# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: michalpirchala

import json
from collections import Counter
from operator import itemgetter

from dateutil import rrule
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.contrib.syndication.views import Feed
from django.db import transaction
from django.db.models import Count, Q
from django.forms.models import BaseModelFormSet, inlineformset_factory
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import feedgenerator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView, TemplateView, UpdateView, View
from django_context_decorator import context

from pretalx.agenda.rules import is_agenda_submission_visible
from pretalx.common.exceptions import SubmissionError
from pretalx.common.forms.fields import SizeFileInput
from pretalx.common.models import ActivityLog
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import json_roundtrip
from pretalx.common.ui import Button, back_button
from pretalx.common.views.generic import (
    CreateOrUpdateView,
    OrgaCRUDView,
    OrgaTableMixin,
    get_next_url,
)
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    EventPermissionRequired,
    PaginationMixin,
    PermissionRequired,
)
from pretalx.mail.models import MailTemplateRoles
from pretalx.orga.forms.submission import (
    AddSpeakerForm,
    AddSpeakerInlineForm,
    AnonymiseForm,
    SubmissionForm,
    SubmissionStateChangeForm,
)
from pretalx.orga.tables.submission import SubmissionTable, TagTable
from pretalx.person.models import User
from pretalx.person.rules import is_only_reviewer
from pretalx.submission.forms import (
    QuestionsForm,
    ResourceForm,
    SubmissionCommentForm,
    SubmissionFilterForm,
    TagForm,
)
from pretalx.submission.models import (
    Feedback,
    QuestionTarget,
    QuestionVariant,
    Resource,
    Submission,
    SubmissionComment,
    SubmissionStates,
    Tag,
)
from pretalx.submission.rules import (
    annotate_assigned,
    get_reviewer_tracks,
    limit_for_reviewers,
    questions_for_user,
)


class SubmissionViewMixin(PermissionRequired):
    def _get_submission_queryset(self):
        return (
            Submission.objects.filter(event=self.request.event)
            .select_related(
                "event", "event__cfp", "submission_type", "track", "event__organiser"
            )
            .prefetch_related(
                "speakers",
                "tags",
                "slots",
                "answers",
                "answers__question",
            )
        )

    def get_queryset(self):
        return self._get_submission_queryset()

    def get_object(self):
        return self.object

    def get_permission_object(self):
        return self.object

    @cached_property
    def object(self):
        return get_object_or_404(
            self.get_queryset(),
            code__iexact=self.kwargs.get("code"),
        )

    @context
    @cached_property
    def submission(self):
        return self.object

    @context
    @cached_property
    def has_anonymised_review(self):
        return self.request.event.review_phases.filter(
            can_see_speaker_names=False
        ).exists()

    @context
    @cached_property
    def is_publicly_visible(self):
        # Check if an anonymous user could see this submission's page
        return is_agenda_submission_visible(None, self.object)


class ReviewerSubmissionFilter:
    @cached_property
    def is_only_reviewer(self):
        return is_only_reviewer(self.request.user, self.request.event)

    @cached_property
    def limit_tracks(self):
        if self.is_only_reviewer:
            return get_reviewer_tracks(self.request.event, self.request.user)

    def get_queryset(self, for_review=False):
        queryset = (
            self.request.event.submissions.all()
            .select_related(
                "submission_type",
                "event",
                "track",
                "submission_type__event",
                "submission_type__event__cfp",
            )
            .prefetch_related("speakers")
        )
        if self.is_only_reviewer:
            queryset = limit_for_reviewers(
                queryset, self.request.event, self.request.user, self.limit_tracks
            )
        if for_review or "is_reviewer" in self.request.user.get_permissions_for_event(
            self.request.event
        ):
            queryset = annotate_assigned(
                queryset, self.request.event, self.request.user
            )
        return queryset


class SubmissionStateChange(SubmissionViewMixin, FormView):
    form_class = SubmissionStateChangeForm
    permission_required = "submission.state_change_submission"
    template_name = "orga/submission/state_change.html"
    TARGETS = {
        "submit": SubmissionStates.SUBMITTED,
        "accept": SubmissionStates.ACCEPTED,
        "reject": SubmissionStates.REJECTED,
        "confirm": SubmissionStates.CONFIRMED,
        "delete": SubmissionStates.DELETED,
        "withdraw": SubmissionStates.WITHDRAWN,
        "cancel": SubmissionStates.CANCELED,
    }

    @cached_property
    def _target(self) -> str:
        """Returns one of
        submit|accept|reject|confirm|delete|withdraw|cancel."""
        return self.TARGETS[self.request.resolver_match.url_name.split(".")[-1]]

    @context
    def target(self):
        return self._target

    def do(self, force=False, pending=False):
        if pending:
            self.object.pending_state = self._target
            self.object.save()
            if self.object.pending_state in SubmissionStates.accepted_states:
                # allow configureability of pending accepted/confirmed talks
                self.object.update_talk_slots()
        else:
            method = getattr(self.object, SubmissionStates.method_names[self._target])
            method(person=self.request.user, force=force, orga=True)

    @transaction.atomic
    def form_valid(self, form):
        if self._target == self.object.state and not self.object.pending_state:
            messages.info(
                self.request,
                _(
                    "Somebody else was faster than you: this proposal was already in the state you wanted to change it to."
                ),
            )
            return redirect(self.get_success_url())

        current = self.object.state
        pending = form.cleaned_data.get("pending")
        try:
            self.do(pending=pending)
        except SubmissionError:
            self.do(force=True, pending=pending)

        if pending:
            return redirect(self.get_success_url())

        check_mail_template = {
            (
                SubmissionStates.ACCEPTED,
                SubmissionStates.REJECTED,
            ): self.request.event.get_mail_template(
                MailTemplateRoles.SUBMISSION_ACCEPT
            ),
            (
                SubmissionStates.REJECTED,
                SubmissionStates.ACCEPTED,
            ): self.request.event.get_mail_template(
                MailTemplateRoles.SUBMISSION_REJECT
            ),
        }
        if template := check_mail_template.get((current, self.object.state)):
            pending_emails = self.request.event.queued_mails.filter(
                template=template,
                sent__isnull=True,
                to_users__in=self.object.speakers.all(),
            )
            if pending_emails.exists():
                messages.warning(
                    self.request,
                    _(
                        "There may be pending emails for this proposal that are now incorrect or outdated."
                    ),
                )
        return redirect(self.get_success_url())

    def get_success_url(self):
        if self.object.state == SubmissionStates.DELETED and (
            not self.next_url or self.object.code in self.next_url
        ):
            return self.request.event.orga_urls.submissions
        return self.next_url or self.request.event.orga_urls.submissions

    @context
    @cached_property
    def next_url(self):
        return get_next_url(self.request)

    @context
    def submit_buttons_extra(self):
        return [back_button(self.next_url or self.object.orga_urls.base)]

    @context
    def submit_buttons(self):
        return [Button(label=_("Do it"))]


class SubmissionSpeakersDelete(SubmissionViewMixin, View):
    permission_required = "submission.update_submission"

    def dispatch(self, request, *args, **kwargs):
        super().dispatch(request, *args, **kwargs)
        submission = self.object
        speaker = get_object_or_404(User, pk=request.GET.get("id"))

        if submission in speaker.submissions.all():
            submission.remove_speaker(speaker, user=self.request.user)
            messages.success(
                request, _("The speaker has been removed from the proposal.")
            )
        else:
            messages.warning(request, _("The speaker was not part of this proposal."))
        return redirect(submission.orga_urls.speakers)


class SubmissionSpeakers(ReviewerSubmissionFilter, SubmissionViewMixin, FormView):
    template_name = "orga/submission/speakers.html"
    permission_required = "person.orga_list_speakerprofile"
    form_class = AddSpeakerInlineForm

    @context
    @cached_property
    def speakers(self):
        submission = self.object
        return [
            {
                "user": speaker,
                "profile": speaker.event_profile(submission.event),
                "other_submissions": speaker.submissions.filter(
                    event=submission.event
                ).exclude(code=submission.code),
            }
            for speaker in submission.speakers.all()
        ]

    def form_valid(self, form):
        if email := form.cleaned_data.get("email"):
            speaker = self.object.add_speaker(
                email=email,
                name=form.cleaned_data.get("name"),
                locale=form.cleaned_data.get("locale"),
                user=self.request.user,
            )
            messages.success(
                self.request, _("The speaker has been added to the proposal.")
            )
            return redirect(speaker.event_profile(self.request.event).orga_urls.base)
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def get_success_url(self):
        return self.object.orga_urls.speakers


class SubmissionContent(
    ReviewerSubmissionFilter, SubmissionViewMixin, CreateOrUpdateView
):
    model = Submission
    form_class = SubmissionForm
    read_only_form_class = True
    template_name = "orga/submission/content.html"
    permission_required = "submission.orga_list_submission"
    extra_forms_signal = "pretalx.orga.signals.submission_form"
    messages = {"update": _("The proposal has been updated!")}

    @cached_property
    def object(self):
        try:
            return get_object_or_404(
                self.get_queryset(),
                code__iexact=self.kwargs.get("code"),
            )
        except Http404 as not_found:
            if self.request.path.rstrip("/").endswith("/new"):
                return None
            return not_found

    @cached_property
    def write_permission_required(self):
        return "submission.update_submission"

    @cached_property
    def create_permission_required(self):
        return "submission.create_submission"

    @context
    def size_warning(self):
        return SizeFileInput.get_size_warning()

    @cached_property
    def _formset(self):
        formset_class = inlineformset_factory(
            Submission,
            Resource,
            form=ResourceForm,
            formset=BaseModelFormSet,
            can_delete=True,
            extra=0,
        )
        return formset_class(
            self.request.POST if self.request.method == "POST" else None,
            files=self.request.FILES if self.request.method == "POST" else None,
            queryset=(
                self.submission.resources.all()
                if self.submission
                else Resource.objects.none()
            ),
            prefix="resource",
        )

    @context
    def formset(self):
        return self._formset

    @context
    @cached_property
    def new_speaker_form(self):
        if not self.submission:
            return AddSpeakerForm(
                data=self.request.POST if self.request.method == "POST" else None,
                event=self.request.event,
                prefix="speaker",
            )

    @cached_property
    def _questions_form(self):
        form_kwargs = self.get_form_kwargs()
        kwargs = {
            "data": self.request.POST if self.request.method == "POST" else None,
            "files": self.request.FILES if self.request.method == "POST" else None,
            "target": "submission",
            "submission": self.submission,
            "event": self.request.event,
            "for_reviewers": (
                not self.request.user.has_perm(
                    "submission.orga_update_submission", self.request.event
                )
                and self.request.user.has_perm(
                    "submission.list_review", self.request.event
                )
            ),
            "readonly": form_kwargs["read_only"],
        }
        # When creating a new submission, filter out track/type specific questions
        if not self.submission:
            kwargs["skip_limited_questions"] = True
        return QuestionsForm(**kwargs)

    @context
    def questions_form(self):
        return self._questions_form

    @context
    def submit_buttons(self):
        return [Button()]

    def save_formset(self, obj):
        if not self._formset.is_valid():
            return False

        for form in self._formset.initial_forms:
            if form in self._formset.deleted_forms:
                if not form.instance.pk:
                    continue
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.instance.submission = obj
                form.save()

        extra_forms = [
            form
            for form in self._formset.extra_forms
            if form.has_changed
            and not self._formset._should_delete_form(form)
            and form.is_valid()
        ]
        for form in extra_forms:
            form.instance.submission = obj
            form.save()

        return True

    def get_permission_required(self):
        if self.permission_action != "create":
            return ["submission.orga_list_submission"]
        return ["submission.create_submission"]

    @property
    def permission_object(self):
        return self.object or self.request.event

    def get_permission_object(self):
        return self.permission_object

    def get_success_url(self) -> str:
        return self.object.orga_urls.base

    @transaction.atomic()
    def form_valid(self, form):
        created = not form.instance.pk
        speaker_form = self.new_speaker_form
        if speaker_form and not speaker_form.is_valid():
            return self.form_invalid(form)
        self.object = form.instance
        self._questions_form.submission = form.instance
        if not self._questions_form.is_valid():
            messages.error(self.request, phrases.base.error_saving_changes)
            return self.get(self.request, *self.args, **self.kwargs)

        old_submission_data = {}
        old_questions_data = {}
        if not created:
            old_submission = form.instance.__class__.objects.get(pk=form.instance.pk)
            old_submission_data = old_submission._get_instance_data() or {}
            old_questions_data = self._questions_form.serialize_answers() or {}

        form.instance.event = self.request.event

        # Save the form and show success message (skipping FormLoggingMixin's logging)
        result = super().form_valid(form, skip_logging=True)
        self.object = form.instance
        self._questions_form.save()

        stay_on_page = False
        if created:
            if speaker_form and (email := speaker_form.cleaned_data["email"]):
                form.instance.add_speaker(
                    email=email,
                    name=self.new_speaker_form.cleaned_data["name"],
                    locale=self.new_speaker_form.cleaned_data.get("locale"),
                    user=self.request.user,
                )
        else:
            if not self.save_formset(form.instance):  # validation failed
                stay_on_page = True

        if message := self.messages.get(self.permission_action):
            messages.success(self.request, message)

        if not created and (
            form.has_changed()
            or self._questions_form.has_changed()
            or self._formset.has_changed()
        ):
            self.request.event.cache.set("rebuild_schedule_export", True, None)
            if not created:
                new_submission_data = form.instance._get_instance_data() or {}
                new_questions_data = self._questions_form.serialize_answers() or {}
                form.instance.log_action(
                    ".update",
                    person=self.request.user,
                    orga=True,
                    old_data=json_roundtrip(old_submission_data | old_questions_data),
                    new_data=json_roundtrip(new_submission_data | new_questions_data),
                )
        elif created:
            form.instance.log_action(".create", person=self.request.user, orga=True)
        if stay_on_page:
            return self.get(self.request, *self.args, **self.kwargs)
        return result

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        instance = kwargs.get("instance")
        kwargs["anonymise"] = getattr(
            instance, "pk", None
        ) and not self.request.user.has_perm(
            "person.orga_list_speakerprofile", instance
        )
        kwargs["read_only"] = kwargs["read_only"] or kwargs["anonymise"]
        return kwargs

    @context
    @cached_property
    def can_edit(self):
        return self.object and self.request.user.has_perm(
            "submission.orga_update_submission", self.request.event
        )


class SubmissionListMixin(ReviewerSubmissionFilter, OrgaTableMixin):
    model = Submission
    table_class = SubmissionTable
    context_object_name = "submissions"
    filter_fields = ()
    usable_states = None

    def get_filter_form(self):
        return SubmissionFilterForm(
            data=self.request.GET,
            event=self.request.event,
            usable_states=self.usable_states,
            limit_tracks=self.limit_tracks,
            search_fields=self.get_default_filters(),
        )

    @context
    @cached_property
    def filter_form(self):
        return self.get_filter_form()

    def get_default_filters(self, *args, **kwargs):
        default_filters = {"code__icontains", "title__icontains"}
        if self.request.user.has_perm(
            "person.orga_list_speakerprofile", self.request.event
        ):
            default_filters.add("speakers__name__icontains")
        return default_filters

    def _get_base_queryset(self, for_review=False):
        # If somebody has *only* reviewer permissions for this event, they can only
        # see the proposals they can review.
        qs = super().get_queryset(for_review=for_review).order_by("-id")
        if not self.filter_form.is_valid():
            return qs
        return self.filter_form.filter_queryset(qs)

    def get_queryset(self):
        return (
            self._get_base_queryset()
            .order_by("id")
            .distinct()
            .select_related("event", "event__cfp")
        )

    @context
    @cached_property
    def short_questions(self):
        return questions_for_user(
            self.request.event, self.request.user, for_answers=True
        ).filter(
            target=QuestionTarget.SUBMISSION,
            variant__in=QuestionVariant.short_answers,
        )

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        can_change_submission = self.request.user.has_perm(
            "submission.orga_update_submission", self.request.event
        )

        exclude = []
        if not self.show_tracks:
            exclude.append("track")
        if not self.show_submission_types:
            exclude.append("submission_type")

        kwargs.update(
            {
                "can_view_speakers": self.request.user.has_perm(
                    "person.orga_list_speakerprofile", self.request.event
                ),
                "has_update_permission": can_change_submission,
                "has_delete_permission": can_change_submission,
                "short_questions": self.short_questions,
                "exclude": exclude,
            }
        )
        return kwargs

    @context
    @cached_property
    def show_tracks(self):
        if self.request.event.feature_flags["use_tracks"]:
            if self.limit_tracks:
                return len(self.limit_tracks) > 1
            return self.request.event.tracks.all().count() > 1

    @context
    @cached_property
    def show_submission_types(self):
        return self.request.event.submission_types.all().count() > 1


class SubmissionList(SubmissionListMixin, EventPermissionRequired, ListView):
    template_name = "orga/submission/list.html"
    permission_required = "submission.orga_list_submission"

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by("state", "pending_state")

    @context
    @cached_property
    def pending_changes(self):
        return self.get_queryset().filter(pending_state__isnull=False).count()


class FeedbackList(SubmissionViewMixin, PaginationMixin, ListView):
    template_name = "orga/submission/feedback_list.html"
    context_object_name = "feedback"
    permission_required = "submission.view_feedback_submission"

    def get_queryset(self):
        return self.submission.feedback.all().order_by("pk")

    @context
    @cached_property
    def submission(self):
        return get_object_or_404(
            self._get_submission_queryset(),
            code__iexact=self.kwargs.get("code"),
        )

    @context
    @cached_property
    def object(self):
        return self.submission

    def get_permission_object(self):
        return self.submission


class ToggleFeatured(SubmissionViewMixin, View):
    permission_required = "submission.orga_update_submission"

    def get_permission_object(self):
        return self.object or self.request.event

    def post(self, *args, **kwargs):
        self.object.is_featured = not self.object.is_featured
        self.object.save(update_fields=["is_featured"])
        return HttpResponse()


class ApplyPending(SubmissionViewMixin, View):
    permission_required = "submission.state_change_submission"

    def post(self, request, *args, **kwargs):
        submission = self.object
        try:
            submission.apply_pending_state(person=request.user)
        except Exception:
            submission.apply_pending_state(person=request.user, force=True)
        return redirect(submission.orga_urls.base)


class Anonymise(SubmissionViewMixin, UpdateView):
    permission_required = "submission.orga_update_submission"
    write_permission_required = "submission.orga_update_submission"
    template_name = "orga/submission/anonymise.html"
    form_class = AnonymiseForm

    def get_permission_object(self):
        return self.object or self.request.event

    @cached_property
    def next_unanonymised(self):
        return self.request.event.submissions.filter(
            Q(anonymised_data="{}") | Q(anonymised_data__isnull=True)
        ).first()

    def form_valid(self, form):
        if self.object.is_anonymised:
            message = _("The anonymisation has been updated.")
        else:
            message = _("This proposal is now marked as anonymised.")
        form.save()
        messages.success(self.request, message)
        if self.request.POST.get("action", "save") == "next" and self.next_unanonymised:
            return redirect(self.next_unanonymised.orga_urls.anonymise)
        return redirect(self.object.orga_urls.anonymise)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons"] = [Button(name="action", value="save")]
        if self.next_unanonymised:
            context["submit_buttons"] += [
                Button(
                    name="action",
                    value="next",
                    label=_("Save and go to next unanonymised"),
                    icon="arrow-right",
                    color="info",
                )
            ]
        return context


class SubmissionHistory(SubmissionViewMixin, ListView):
    template_name = "orga/submission/history.html"
    permission_required = "person.orga_list_speakerprofile"
    paginate_by = 200
    context_object_name = "log_entries"

    @context
    @cached_property
    def submission(self):
        return get_object_or_404(
            Submission.objects.filter(event=self.request.event),
            code__iexact=self.kwargs.get("code"),
        )

    @context
    @cached_property
    def object(self):
        return self.submission

    def get_queryset(self):
        # TODO: This does not include everything regarding this submission. Missing:
        # - scheduling changes
        # - new comments
        # - new feedback
        # - emails sent to speakers (important?)
        # - reviews written and changes
        return self.submission.logged_actions().all()

    def get_permission_object(self):
        return self.request.event


class SubmissionFeed(Feed):
    permission_required = "submission.orga_list_submission"
    feed_type = feedgenerator.Atom1Feed

    def get_object(self, request, *args, **kwargs):
        event = request.event
        if not request.user.has_perm("submission.orga_list_submission", event):
            raise Http404()
        return event

    def title(self, obj):
        return _("{name} proposal feed").format(name=obj.name)

    def link(self, obj):
        return obj.orga_urls.submissions.full()

    def feed_url(self, obj):
        return obj.orga_urls.submission_feed.full()

    def feed_guid(self, obj):
        return obj.orga_urls.submission_feed.full()

    def description(self, obj):
        return _("Updates to the {name} schedule.").format(name=obj.name)

    def items(self, obj):
        return obj.submissions.order_by("-pk")

    def item_title(self, item):
        return _("New {event} proposal: {title}").format(
            event=item.event.name, title=item.title
        )

    def item_link(self, item):
        return item.orga_urls.base.full()

    def item_pubdate(self, item):
        return item.created


class SubmissionStats(EventPermissionRequired, TemplateView):
    template_name = "orga/submission/stats.html"
    permission_required = "submission.orga_list_submission"

    @context
    def show_submission_types(self):
        return self.request.event.submission_types.all().count() > 1

    @context
    def id_mapping(self):
        data = {
            "type": {
                str(submission_type): submission_type.id
                for submission_type in self.request.event.submission_types.all()
            },
            "state": {
                str(value): key
                for key, value in SubmissionStates.display_values.items()
            },
        }
        if self.show_tracks:
            data["track"] = {
                str(track): track.id for track in self.request.event.tracks.all()
            }
        return json.dumps(data)

    @context
    @cached_property
    def show_tracks(self):
        return (
            self.request.event.get_feature_flag("use_tracks")
            and self.request.event.tracks.all().count() > 1
        )

    @context
    def timeline_annotations(self):
        deadlines = [
            (
                submission_type.deadline.astimezone(self.request.event.tz).strftime(
                    "%Y-%m-%d"
                ),
                str(_("Deadline")) + f" ({submission_type.name})",
            )
            for submission_type in self.request.event.submission_types.filter(
                deadline__isnull=False
            )
        ]
        if self.request.event.cfp.deadline:
            deadlines.append(
                (
                    self.request.event.cfp.deadline.astimezone(
                        self.request.event.tz
                    ).strftime("%Y-%m-%d"),
                    str(_("Deadline")),
                )
            )
        return json.dumps({"deadlines": deadlines})

    @cached_property
    def raw_submission_timeline_data(self):
        talk_ids = self.request.event.submissions.exclude(
            state=SubmissionStates.DELETED
        ).values_list("id", flat=True)
        data = Counter(
            log.timestamp.astimezone(self.request.event.tz).date()
            for log in ActivityLog.objects.filter(
                event=self.request.event,
                action_type="pretalx.submission.create",
                content_type=ContentType.objects.get_for_model(Submission),
                object_id__in=talk_ids,
            )
        )
        dates = data.keys()
        if len(dates) > 1:
            date_range = rrule.rrule(
                rrule.DAILY,
                count=(max(dates) - min(dates)).days + 1,
                dtstart=min(dates),
            )
            return sorted(
                (
                    {"x": date.date().isoformat(), "y": data.get(date.date(), 0)}
                    for date in date_range
                ),
                key=lambda x: x["x"],
            )

    @context
    def submission_timeline_data(self):
        if self.raw_submission_timeline_data:
            return json.dumps(self.raw_submission_timeline_data)
        return ""

    @context
    def total_submission_timeline_data(self):
        if self.raw_submission_timeline_data:
            result = [{"x": 0, "y": 0}]
            for point in self.raw_submission_timeline_data:
                result.append({"x": point["x"], "y": result[-1]["y"] + point["y"]})
            return json.dumps(result[1:])
        return ""

    @context
    @cached_property
    def submission_state_data(self):
        counter = Counter(
            submission.get_state_display()
            for submission in Submission.all_objects.exclude(
                state=SubmissionStates.DRAFT
            ).filter(event=self.request.event)
        )
        return json.dumps(
            sorted(
                [{"label": label, "value": value} for label, value in counter.items()],
                key=itemgetter("label"),
            )
        )

    @context
    def submission_type_data(self):
        counter = Counter(
            str(submission.submission_type)
            for submission in Submission.objects.filter(
                event=self.request.event
            ).select_related("submission_type")
        )
        return json.dumps(
            sorted(
                [{"label": label, "value": value} for label, value in counter.items()],
                key=itemgetter("label"),
            )
        )

    @context
    def submission_track_data(self):
        if self.request.event.get_feature_flag("use_tracks"):
            counter = Counter(
                str(submission.track)
                for submission in Submission.objects.filter(
                    event=self.request.event
                ).select_related("track")
            )
            return json.dumps(
                sorted(
                    [
                        {"label": label, "value": value}
                        for label, value in counter.items()
                    ],
                    key=itemgetter("label"),
                )
            )
        return ""

    @context
    def talk_timeline_data(self):
        talk_ids = self.request.event.submissions.filter(
            state__in=SubmissionStates.accepted_states
        ).values_list("id", flat=True)
        data = Counter(
            log.timestamp.astimezone(self.request.event.tz).date().isoformat()
            for log in ActivityLog.objects.filter(
                event=self.request.event,
                action_type="pretalx.submission.create",
                content_type=ContentType.objects.get_for_model(Submission),
                object_id__in=talk_ids,
            )
        )
        if len(data.keys()) > 1:
            return json.dumps(
                [
                    {"x": point["x"], "y": data.get(point["x"][:10], 0)}
                    for point in self.raw_submission_timeline_data
                ]
            )
        return ""

    @context
    def talk_state_data(self):
        counter = Counter(
            submission.get_state_display()
            for submission in self.request.event.submissions.filter(
                state__in=SubmissionStates.accepted_states
            )
        )
        return json.dumps(
            sorted(
                [{"label": label, "value": value} for label, value in counter.items()],
                key=itemgetter("label"),
            )
        )

    @context
    def talk_type_data(self):
        counter = Counter(
            str(submission.submission_type)
            for submission in self.request.event.submissions.filter(
                state__in=SubmissionStates.accepted_states
            ).select_related("submission_type")
        )
        return json.dumps(
            sorted(
                [{"label": label, "value": value} for label, value in counter.items()],
                key=itemgetter("label"),
            )
        )

    @context
    def talk_track_data(self):
        if self.request.event.get_feature_flag("use_tracks"):
            counter = Counter(
                str(submission.track)
                for submission in self.request.event.submissions.filter(
                    state__in=SubmissionStates.accepted_states
                ).select_related("track")
            )
            return json.dumps(
                sorted(
                    [
                        {"label": label, "value": value}
                        for label, value in counter.items()
                    ],
                    key=itemgetter("label"),
                )
            )
        return ""


class AllFeedbacksList(EventPermissionRequired, PaginationMixin, ListView):
    model = Feedback
    context_object_name = "feedback"
    template_name = "orga/submission/feedbacks_list.html"
    permission_required = "submission.orga_list_submission"

    def get_queryset(self):
        return (
            Feedback.objects.order_by("-pk")
            .select_related("talk")
            .filter(talk__event=self.request.event)
        )


class TagView(OrgaCRUDView):
    model = Tag
    form_class = TagForm
    table_class = TagTable
    template_namespace = "orga/submission"
    create_button_label = _("New tag")

    def get_queryset(self):
        return (
            self.request.event.tags.all()
            .order_by("tag")
            .annotate(submission_count=Count("submissions"))
        )

    def get_generic_title(self, instance=None):
        if instance:
            return (
                _("Tag")
                + f" {phrases.base.quotation_open}{instance.tag}{phrases.base.quotation_close}"
            )
        if self.action == "create":
            return _("New tag")
        return _("Tags")


class CommentList(SubmissionViewMixin, FormView):
    template_name = "orga/submission/comments.html"
    permission_required = "submission.view_submissioncomment"
    write_permission_required = "submission.create_submissioncomment"
    form_class = SubmissionCommentForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["submission"] = self.object
        kwargs["user"] = self.request.user
        return kwargs

    @context
    @cached_property
    def comments(self):
        return self.object.comments.all().select_related("user").order_by("created")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, phrases.base.saved)
        return redirect(self.object.orga_urls.comments)


class CommentDelete(SubmissionViewMixin, ActionConfirmMixin, TemplateView):
    permission_required = "submission.delete_submissioncomment"

    @property
    def action_back_url(self):
        return self.object.submission.orga_urls.comments

    @property
    def action_object_name(self):
        return _("Your comment on “{title}”").format(title=self.object.submission.title)

    @cached_property
    def object(self):
        return get_object_or_404(
            SubmissionComment,
            submission__code__iexact=self.kwargs["code"],
            pk=self.kwargs["pk"],
        )

    def post(self, request, *args, **kwargs):
        comment = self.get_object()
        comment.submission.log_action(
            "pretalx.submission.comment.delete", person=request.user, orga=True
        )
        comment.delete()
        messages.success(request, _("The comment has been deleted."))
        return redirect(comment.submission.orga_urls.comments)


class ApplyPendingBulk(
    EventPermissionRequired, SubmissionListMixin, PaginationMixin, ListView
):
    permission_required = "submission.state_change_submission"
    template_name = "orga/submission/apply_pending.html"

    @cached_property
    def submissions(self):
        return self.get_queryset().filter(pending_state__isnull=False)

    @context
    @cached_property
    def submission_count(self):
        return len(self.submissions)

    def post(self, request, *args, **kwargs):
        for submission in self.submissions:
            try:
                submission.apply_pending_state(person=self.request.user)
            except Exception:
                submission.apply_pending_state(person=self.request.user, force=True)
        messages.success(
            self.request,
            str(_("Changed {count} proposal states.")).format(
                count=self.submission_count
            ),
        )
        return redirect(self.next_url)

    @cached_property
    def next_url(self):
        return get_next_url(self.request) or self.request.event.orga_urls.submissions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons_extra"] = [back_button(self.next_url)]
        if self.submission_count:
            context["submit_buttons"] = [Button(label=_("Do it"))]
        return context
