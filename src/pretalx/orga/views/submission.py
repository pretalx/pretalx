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
from django.db import transaction
from django.db.models import Count, Q
from django.forms.models import BaseModelFormSet, inlineformset_factory
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView, TemplateView, UpdateView, View
from django_context_decorator import context

from pretalx.agenda.rules import is_agenda_submission_visible
from pretalx.common.exceptions import SubmissionError
from pretalx.common.forms import save_related_formset
from pretalx.common.forms.fields import SizeFileInput
from pretalx.common.models import ActivityLog
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import json_roundtrip
from pretalx.common.ui import Button, back_button
from pretalx.common.views.generic import (
    CreateOrUpdateView,
    OrgaCRUDView,
    OrgaTableMixin,
)
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    EventPermissionRequired,
    PaginationMixin,
    PermissionRequired,
)
from pretalx.common.views.redirect import get_next_url
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.orga.forms.submission import (
    AddSpeakerForm,
    AddSpeakerInlineForm,
    SubmissionStateChangeForm,
)
from pretalx.orga.tables.feedback import FeedbackTable
from pretalx.orga.tables.signup import AttendeeSignupTable
from pretalx.orga.tables.submission import SubmissionTable, TagTable
from pretalx.person.models import SpeakerProfile
from pretalx.person.rules import is_only_reviewer
from pretalx.submission.domain.cfp import cfp_deadlines
from pretalx.submission.domain.invitation import retract_invitation
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.queries.submission import (
    annotate_assigned_reviews,
    annotate_confirmed_signup_count,
    annotate_requires_signup,
    annotate_submission_count,
    submissions_for_user,
)
from pretalx.submission.domain.submission import (
    apply_pending_state,
    create_submission,
    delete_submission,
    invite_speaker,
    remove_speaker,
    reorder_speakers,
    set_pending_state,
    set_submission_state,
    set_wip_slot,
)
from pretalx.submission.interfaces.forms import (
    AnonymiseForm,
    QuestionsForm,
    ResourceForm,
    SubmissionCommentForm,
    SubmissionFilterForm,
    SubmissionOrgaForm,
    SubmissionSignupFilterForm,
    SubmissionSignupForm,
    TagForm,
)
from pretalx.submission.models import (
    Feedback,
    QuestionTarget,
    QuestionVariant,
    Resource,
    Submission,
    SubmissionComment,
    SubmissionInvitation,
    SubmissionStates,
    Tag,
)
from pretalx.submission.models.submission import SpeakerRole
from pretalx.submission.rules import (
    has_reviewer_access,
    orga_can_change_submissions,
    submission_comments_active,
)


class SubmissionViewMixin(PermissionRequired):
    def _get_submission_queryset(self):
        return self._annotate_for_signup(
            submissions_for_user(self.request.event, self.request.user)
            .select_related(
                "event__cfp", "event__organiser", "track", "submission_type"
            )
            .prefetch_related(
                "speakers", "tags", "slots", "answers", "answers__question"
            )
        )

    def _get_lightweight_submission_queryset(self):
        """select_related only, no prefetches. Use this in sub-views that
        don't render speakers, tags, slots or answers (FeedbackList,
        CommentList) – the full queryset is the default because
        SubmissionContent needs all those relations for the main edit form."""
        return self._annotate_for_signup(
            submissions_for_user(self.request.event, self.request.user).select_related(
                "event__cfp", "event__organiser", "track", "submission_type"
            )
        )

    def _annotate_for_signup(self, queryset):
        if not self.request.event.get_feature_flag("attendee_signup"):
            return queryset
        return annotate_confirmed_signup_count(annotate_requires_signup(queryset))

    def get_queryset(self):
        return self._get_submission_queryset()

    def get_object(self):
        return self.object

    def get_permission_object(self):
        return self.object

    @cached_property
    def object(self):
        return get_object_or_404(
            self.get_queryset(), code__iexact=self.kwargs.get("code")
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
            return self.request.user.get_reviewer_tracks(self.request.event)

    def get_queryset(self):
        queryset = (
            submissions_for_user(self.request.event, self.request.user)
            .select_related(
                "track__event",
                "track__event__cfp",
                "submission_type__event",
                "submission_type__event__cfp",
            )
            .with_sorted_speakers()
        )
        return annotate_assigned_reviews(
            queryset, self.request.event, self.request.user
        )


class SubmissionStateChange(SubmissionViewMixin, FormView):
    form_class = SubmissionStateChangeForm
    permission_required = "submission.state_change_submission"
    template_name = "orga/submission/state_change.html"
    TARGETS = {
        "submit": SubmissionStates.SUBMITTED,
        "accept": SubmissionStates.ACCEPTED,
        "reject": SubmissionStates.REJECTED,
        "confirm": SubmissionStates.CONFIRMED,
        "withdraw": SubmissionStates.WITHDRAWN,
        "cancel": SubmissionStates.CANCELED,
    }

    @cached_property
    def _action(self) -> str:
        """Returns one of submit|accept|reject|confirm|withdraw|cancel."""
        return self.request.resolver_match.url_name.split(".")[-1]

    @cached_property
    def _target(self):
        """Returns the target state, or None for delete action."""
        return self.TARGETS.get(self._action)

    @context
    def target(self):
        return self._target

    def do(self, pending=False):
        if pending:
            set_pending_state(self.object, self._target)
        else:
            set_submission_state(
                self.object, self._target, person=self.request.user, orga=True
            )

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
        except SubmissionError as e:
            messages.error(self.request, str(e))
            return redirect(self.get_success_url())

        if pending:
            return redirect(self.get_success_url())

        check_mail_template = {
            (
                SubmissionStates.ACCEPTED,
                SubmissionStates.REJECTED,
            ): mail_template_by_role(
                self.request.event, MailTemplateRoles.SUBMISSION_ACCEPT
            ),
            (
                SubmissionStates.REJECTED,
                SubmissionStates.ACCEPTED,
            ): mail_template_by_role(
                self.request.event, MailTemplateRoles.SUBMISSION_REJECT
            ),
        }
        if template := check_mail_template.get((current, self.object.state)):
            pending_emails = self.request.event.queued_mails.filter(
                template=template,
                state=QueuedMailStates.DRAFT,
                to_users__in=self.object.speakers.values_list("user", flat=True),
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


class SubmissionDelete(SubmissionViewMixin, ActionConfirmMixin, TemplateView):
    permission_required = "submission.state_change_submission"
    template_name = "orga/submission/delete.html"
    action_object_name = ""  # Submission is listed in the template header

    @property
    def action_text(self):
        current_slots = self.object.current_slots
        has_scheduled_slots = current_slots is not None and current_slots.exists()
        if has_scheduled_slots:
            return _(
                "This session is part of the current schedule. All its schedule "
                "slots will also be deleted. You may want to set it to the "
                '"withdrawn" state instead.'
            )
        return phrases.base.delete_warning

    @property
    def action_back_url(self):
        return get_next_url(self.request) or self.object.orga_urls.base

    def post(self, request, *args, **kwargs):
        submission = self.object
        delete_submission(submission, person=request.user, orga=True)
        messages.success(request, _("The proposal has been deleted."))
        return redirect(request.event.orga_urls.submissions)


class SubmissionSpeakersDelete(SubmissionViewMixin, View):
    permission_required = "submission.update_submission"

    def post(self, request, *args, **kwargs):
        submission = self.object
        speaker = get_object_or_404(
            SpeakerProfile, pk=request.POST.get("id"), event=request.event
        )

        if submission.speakers.filter(pk=speaker.pk).exists():
            remove_speaker(submission, speaker, user=self.request.user)
            messages.success(
                request, _("The speaker has been removed from the proposal.")
            )
        else:
            messages.warning(request, _("The speaker was not part of this proposal."))
        return redirect(submission.orga_urls.speakers)


class SubmissionSpeakersReorder(SubmissionViewMixin, View):
    permission_required = "submission.update_submission"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        order = request.POST.get("order", "")
        if not order:
            return HttpResponse(status=400)
        try:
            reorder_speakers(
                self.object, role_ids=order.split(","), person=request.user, orga=True
            )
        except ValueError:
            return HttpResponse(status=400)
        return HttpResponse(status=204)


class SubmissionInvitationRetract(
    SubmissionViewMixin, ActionConfirmMixin, TemplateView
):
    permission_required = "submission.update_submission"
    action_title = _("Retract invitation")
    action_confirm_color = "danger"
    action_confirm_icon = "trash"
    action_confirm_label = _("Retract")

    @cached_property
    def invitation(self):
        return get_object_or_404(
            SubmissionInvitation, pk=self.request.GET.get("id"), submission=self.object
        )

    @property
    def action_object_name(self):
        return self.invitation.email

    @property
    def action_text(self):
        return _("Do you really want to retract the invitation for {email}?").format(
            email=self.invitation.email
        )

    @property
    def action_back_url(self):
        return self.object.orga_urls.speakers

    def post(self, request, *args, **kwargs):
        retract_invitation(self.invitation, person=request.user, orga=True)
        messages.success(request, _("The invitation has been retracted."))
        return redirect(self.object.orga_urls.speakers)


class SubmissionSpeakers(ReviewerSubmissionFilter, SubmissionViewMixin, FormView):
    template_name = "orga/submission/speakers.html"
    permission_required = "person.orga_list_speakerprofile"
    form_class = AddSpeakerInlineForm

    @context
    @cached_property
    def speakers(self):
        submission = self.object
        roles = {
            role.speaker_id: role
            for role in SpeakerRole.objects.filter(submission=submission)
        }
        return [
            {
                "speaker": speaker,
                "role": roles.get(speaker.pk),
                "other_submissions": speaker.submissions.exclude(code=submission.code),
            }
            for speaker in submission.sorted_speakers
        ]

    @context
    @cached_property
    def invitations(self):
        return self.object.invitations.all()

    def form_valid(self, form):
        if email := form.cleaned_data.get("email"):
            speaker = invite_speaker(
                self.object,
                email=email,
                name=form.cleaned_data.get("name"),
                locale=form.cleaned_data.get("locale"),
                user=self.request.user,
            )
            messages.success(
                self.request, _("The speaker has been added to the proposal.")
            )
            return redirect(speaker.orga_urls.base)
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
    form_class = SubmissionOrgaForm
    read_only_form_class = True
    template_name = "orga/submission/content.html"
    permission_required = "submission.orga_list_submission"
    extra_forms_signal = "pretalx.orga.signals.submission_form"
    messages = {"edit": _("The proposal has been updated!")}

    @cached_property
    def object(self):
        try:
            return get_object_or_404(
                self.get_queryset(), code__iexact=self.kwargs.get("code")
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
    def _resources_enabled(self):
        return self.request.event.cfp.request_resources

    @cached_property
    def _formset(self):
        if not self._resources_enabled:
            return None
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
    def resources_enabled(self):
        return self._resources_enabled

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
            "read_only": form_kwargs["read_only"],
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
        created = form.instance._state.adding
        speaker_form = self.new_speaker_form
        if speaker_form and not speaker_form.is_valid():
            return self.form_invalid(form)
        if not self._questions_form.is_valid():
            messages.error(self.request, phrases.base.error_saving_changes)
            return self.get(self.request, *self.args, **self.kwargs)
        if not created and self._formset and not self._formset.is_valid():
            return self.get(self.request, *self.args, **self.kwargs)
        self.object = form.instance

        old_submission_data = {}
        old_questions_data = {}
        if not created:
            old_submission = form.instance.__class__.objects.get(pk=form.instance.pk)
            old_submission_data = old_submission.get_instance_data() or {}
            old_questions_data = self._questions_form.serialize_answers() or {}

        form.instance.event = self.request.event

        if created:
            try:
                create_submission(
                    submission=form.instance,
                    user=self.request.user,
                    orga=True,
                    tags=form.cleaned_data.get("tags"),
                )
            except SubmissionError as e:
                messages.error(self.request, str(e))
                return redirect(self.request.event.orga_urls.new_submission)
            self.object = form.instance
            result = redirect(self.get_success_url())
        else:
            result = super().form_valid(form, skip_logging=True)
            self.object = form.instance
        if (scheduling := form.scheduling_kwargs()) is not None:
            set_wip_slot(self.object, **scheduling)
        self._questions_form.save(submission=form.instance)

        if created:
            if speaker_form and (email := speaker_form.cleaned_data["email"]):
                invite_speaker(
                    form.instance,
                    email=email,
                    name=self.new_speaker_form.cleaned_data["name"],
                    locale=self.new_speaker_form.cleaned_data.get("locale"),
                    user=self.request.user,
                )
        elif self._formset:
            save_related_formset(
                self._formset, parent=form.instance, fk_field="submission"
            )

        if message := self.messages.get(self.permission_action):
            messages.success(self.request, message)

        if not created and (
            form.has_changed()
            or self._questions_form.has_changed()
            or (self._formset and self._formset.has_changed())
        ):
            new_submission_data = form.instance.get_instance_data() or {}
            new_questions_data = self._questions_form.serialize_answers() or {}
            form.instance.log_action(
                ".update",
                person=self.request.user,
                orga=True,
                old_data=json_roundtrip(old_submission_data | old_questions_data),
                new_data=json_roundtrip(new_submission_data | new_questions_data),
            )
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
        can_view_speakers = self.request.user.has_perm(
            "person.orga_list_speakerprofile", self.request.event
        ) or self.request.user.has_perm(
            "person.reviewer_list_speakerprofile", self.request.event
        )
        return SubmissionFilterForm(
            data=self.request.GET,
            event=self.request.event,
            usable_states=self.usable_states,
            limit_tracks=self.limit_tracks,
            can_view_speakers=can_view_speakers,
        )

    @context
    @cached_property
    def filter_form(self):
        return self.get_filter_form()

    def _get_base_queryset(self):
        # If somebody has *only* reviewer permissions for this event, they can only
        # see the proposals they can review.
        qs = super().get_queryset().order_by("-id")
        if not self.filter_form.is_valid():
            return qs
        return self.filter_form.filter_queryset(qs)

    def get_queryset(self):
        queryset = (
            self._get_base_queryset()
            .order_by("id")
            .distinct()
            .select_related("event", "event__cfp")
            .annotate(
                speaker_count=Count("speakers", distinct=True),
                invitation_count=Count("invitations", distinct=True),
            )
        )
        if self.request.event.get_feature_flag("attendee_signup"):
            queryset = annotate_confirmed_signup_count(
                annotate_requires_signup(queryset)
            )
        return queryset

    @context
    @cached_property
    def short_questions(self):
        return questions_for_user(self.request.event, self.request.user).filter(
            target=QuestionTarget.SUBMISSION, variant__in=QuestionVariant.short_answers
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
        return self.request.event.has_active_tracks

    @context
    @cached_property
    def show_submission_types(self):
        return self.request.event.submission_types.count() > 1


class SubmissionList(SubmissionListMixin, EventPermissionRequired, ListView):
    template_name = "orga/submission/list.html"
    permission_required = "submission.orga_list_submission"

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by("state", "pending_state")

    @context
    @cached_property
    def pending_changes(self):
        return self.request.event.submissions.filter(
            pending_state__isnull=False
        ).count()


class FeedbackList(SubmissionViewMixin, OrgaTableMixin, ListView):
    template_name = "orga/submission/feedback_list.html"
    context_object_name = "feedback"
    permission_required = "submission.view_feedback_submission"
    table_class = FeedbackTable

    def get_queryset(self):
        return (
            self.submission.feedback.all()
            .select_related("talk__event", "speaker", "speaker__user")
            .order_by("-created", "-pk")
        )

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs["include_talk"] = False
        return kwargs

    @context
    @cached_property
    def submission(self):
        return get_object_or_404(
            self._get_lightweight_submission_queryset(),
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
            apply_pending_state(submission, person=request.user)
        except SubmissionError as e:
            messages.error(request, str(e))
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
        return self.request.event.submissions.filter(Q(anonymised__isnull=True)).first()

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


class SubmissionSignup(SubmissionViewMixin, OrgaTableMixin, ListView):
    template_name = "orga/submission/signup.html"
    permission_required = "submission.orga_update_submission"
    context_object_name = "attendee_signups"
    table_class = AttendeeSignupTable
    # No pagination. Rooms have finite size and organisers want
    # to see the attendee list at once (and print it).
    table_pagination = False
    paginate_by = None

    @context
    @cached_property
    def submission(self):
        return get_object_or_404(
            self._get_lightweight_submission_queryset(),
            code__iexact=self.kwargs.get("code"),
        )

    @cached_property
    def object(self):
        return self.submission

    def get_permission_object(self):
        return self.submission

    def dispatch(self, request, *args, **kwargs):
        if not self.submission.requires_signup:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = self.submission.attendee_signups.select_related(
            "attendee", "attendee__user"
        ).order_by("-state", "position")
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_queryset(qs)
        return qs

    @context
    @cached_property
    def filter_form(self):
        return SubmissionSignupFilterForm(
            data=self.request.GET or None, submission=self.submission
        )

    @cached_property
    def capacity_form(self):
        kwargs = {
            "instance": self.submission,
            "read_only": not self.request.user.has_perm(
                "submission.orga_update_submission", self.request.event
            ),
        }
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return SubmissionSignupForm(**kwargs)

    @context
    def form(self):
        return self.capacity_form

    def post(self, request, *args, **kwargs):
        form = self.capacity_form
        if form.is_valid():
            form.save()
            messages.success(self.request, phrases.base.saved)
            return redirect(self.submission.orga_urls.signup)
        return self.get(request, *args, **kwargs)

    @context
    @cached_property
    def attendee_count(self):
        return self.submission.confirmed_signup_count

    @context
    def capacity(self):
        return self.submission.effective_signup_capacity

    @context
    def capacity_percent(self):
        return self.submission.signup_capacity_percent


class SubmissionHistory(SubmissionViewMixin, ListView):
    template_name = "orga/submission/history.html"
    permission_required = "person.orga_list_speakerprofile"
    paginate_by = 200
    context_object_name = "log_entries"

    @context
    @cached_property
    def submission(self):
        return get_object_or_404(
            submissions_for_user(self.request.event, self.request.user),
            code__iexact=self.kwargs.get("code"),
        )

    @context
    @cached_property
    def object(self):
        return self.submission

    def get_queryset(self):
        return self.submission.logged_actions().all()

    def get_permission_object(self):
        return self.request.event


class SubmissionStats(EventPermissionRequired, TemplateView):
    template_name = "orga/submission/stats.html"
    permission_required = "submission.orga_list_submission"

    @cached_property
    def submissions(self):
        return list(submissions_for_user(self.request.event, self.request.user))

    @cached_property
    def accepted_submissions(self):
        return [
            submission
            for submission in self.submissions
            if submission.state in SubmissionStates.accepted_states
        ]

    @context
    def show_submission_types(self):
        return self.request.event.submission_types.count() > 1

    @context
    def id_mapping(self):
        data = {
            "type": {
                str(submission_type): submission_type.id
                for submission_type in self.request.event.submission_types.all()
            },
            "state": {str(value): key for key, value in SubmissionStates.choices},
        }
        if self.show_tracks:
            data["track"] = {
                str(track): track.id for track in self.request.event.tracks.all()
            }
        return json.dumps(data)

    @context
    @cached_property
    def show_tracks(self):
        return self.request.event.has_active_tracks

    @context
    def timeline_annotations(self):
        deadlines = [
            (
                dt.strftime("%Y-%m-%d"),
                (
                    str(_("Deadline")) + f" ({submission_type.name})"
                    if submission_type is not None
                    else str(_("Deadline"))
                ),
            )
            for dt, submission_type in cfp_deadlines(self.request.event)
        ]
        return json.dumps({"deadlines": deadlines})

    @cached_property
    def raw_submission_timeline_data(self):
        talk_ids = [submission.id for submission in self.submissions]
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
            submission.get_state_display() for submission in self.submissions
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
            str(submission.submission_type) for submission in self.submissions
        )
        return json.dumps(
            sorted(
                [{"label": label, "value": value} for label, value in counter.items()],
                key=itemgetter("label"),
            )
        )

    @context
    def submission_track_data(self):
        if self.request.event.has_active_tracks:
            counter = Counter(str(submission.track) for submission in self.submissions)
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
        talk_ids = [submission.id for submission in self.accepted_submissions]
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
            submission.get_state_display() for submission in self.accepted_submissions
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
            str(submission.submission_type) for submission in self.accepted_submissions
        )
        return json.dumps(
            sorted(
                [{"label": label, "value": value} for label, value in counter.items()],
                key=itemgetter("label"),
            )
        )

    @context
    def talk_track_data(self):
        if self.request.event.has_active_tracks:
            counter = Counter(
                str(submission.track) for submission in self.accepted_submissions
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


class AllFeedbacksList(EventPermissionRequired, OrgaTableMixin, ListView):
    model = Feedback
    context_object_name = "feedback"
    template_name = "orga/submission/feedbacks_list.html"
    permission_required = "submission.orga_list_submission"
    table_class = FeedbackTable

    def get_queryset(self):
        submissions = submissions_for_user(self.request.event, self.request.user)
        return (
            Feedback.objects.filter(talk__in=submissions)
            .select_related("talk__event", "speaker", "speaker__user")
            .order_by("-created", "-pk")
        )


class TagView(OrgaCRUDView):
    model = Tag
    form_class = TagForm
    table_class = TagTable
    template_namespace = "orga/submission"
    create_button_label = _("New tag")

    def get_queryset(self):
        return annotate_submission_count(self.request.event.tags.order_by("tag"))

    def get_generic_title(self, instance=None):
        if instance:
            return (
                phrases.submission.tag
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

    def get_queryset(self):
        return self._get_lightweight_submission_queryset()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["submission"] = self.object
        kwargs["user"] = self.request.user
        return kwargs

    @context
    @cached_property
    def comments(self):
        return self.object.comments.select_related("user").order_by("created")

    @context
    @cached_property
    def can_delete_own_comments(self):
        """Pre-compute if the user could delete their own comments."""
        user = self.request.user
        submission = self.object
        return bool(
            submission_comments_active(user, submission)
            and (
                has_reviewer_access(user, submission)
                or orga_can_change_submissions(user, submission)
            )
        )

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

    @transaction.atomic
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
        return self.submissions.count()

    def post(self, request, *args, **kwargs):
        errors = []
        for submission in self.submissions:
            try:
                apply_pending_state(submission, person=self.request.user)
            except SubmissionError as e:
                errors.append(f"{submission.title}: {e}")
        if errors:
            for error in errors:
                messages.error(self.request, error)
        messages.success(
            self.request,
            str(_("Changed {count} proposal states.")).format(
                count=self.submission_count - len(errors)
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
