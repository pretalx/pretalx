# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, FormView, ListView, View
from django_context_decorator import context

from pretalx.common.exceptions import SendMailException
from pretalx.common.exporter import get_schedule_exporters
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import json_roundtrip
from pretalx.common.ui import api_buttons
from pretalx.common.views.generic import (
    CreateOrUpdateView,
    OrgaCRUDView,
    OrgaTableMixin,
)
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    EventPermissionRequired,
    Filterable,
    PermissionRequired,
)
from pretalx.common.views.redirect import get_next_url
from pretalx.mail.enums import QueuedMailStates
from pretalx.orga.forms.export import SpeakerExportForm
from pretalx.orga.forms.submission import AddSpeakerForm
from pretalx.orga.tables.speaker import SpeakerInformationTable, SpeakerTable
from pretalx.person.domain.profile import (
    retract_speaker_invite,
    send_speaker_invite,
    shred_speaker_profile,
)
from pretalx.person.domain.queries.profile import (
    annotate_speaker_submission_counts,
    speaker_name_expression,
)
from pretalx.person.domain.user import reset_password
from pretalx.person.interfaces.forms import (
    SpeakerFilterForm,
    SpeakerInformationForm,
    SpeakerInviteForm,
    SpeakerProfileForm,
)
from pretalx.person.models import SpeakerInformation, SpeakerProfile
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.queries.speaker import speakers_for_user
from pretalx.submission.domain.queries.submission import (
    speaker_search_q,
    submissions_for_user,
)
from pretalx.submission.interfaces.forms import QuestionsForm
from pretalx.submission.models import Answer, QuestionTarget, QuestionVariant
from pretalx.submission.models.submission import SubmissionStates


class SpeakerList(EventPermissionRequired, Filterable, OrgaTableMixin, ListView):
    template_name = "orga/speaker/list.html"
    context_object_name = "speakers"
    table_class = SpeakerTable
    permission_required = "person.orga_list_speakerprofile"

    def handle_search(self, qs, query, filters):
        search = speaker_search_q(query)
        if (
            self.filter_form
            and self.filter_form.is_valid()
            and self.filter_form.cleaned_data.get("fulltext")
        ):
            search |= Q(biography__icontains=query)
        return qs.filter(search)

    def get_filter_form(self):
        any_arrived = self.request.event.submitters.filter(has_arrived=True).exists()
        return SpeakerFilterForm(
            self.request.GET, event=self.request.event, filter_arrival=any_arrived
        )

    def get_queryset(self):
        # Reviewers do not need speakers without submissions
        include_bare = self.request.user.has_perm(
            "submission.orga_update_submission", self.request.event
        )
        qs = annotate_speaker_submission_counts(
            speakers_for_user(
                self.request.event, self.request.user, include_bare=include_bare
            ),
            event=self.request.event,
        )

        qs = self.filter_queryset(qs)

        question = self.request.GET.get("question")
        unanswered = self.request.GET.get("unanswered")
        answer = self.request.GET.get("answer")
        option = self.request.GET.get("answer__options")
        if question and (answer or option):
            if option:
                answers = Answer.objects.filter(
                    speaker_id=OuterRef("pk"), question_id=question, options__pk=option
                )
            else:
                answers = Answer.objects.filter(
                    speaker_id=OuterRef("pk"),
                    question_id=question,
                    answer__exact=answer,
                )
            qs = qs.annotate(has_answer=Exists(answers)).filter(has_answer=True)
        elif question and unanswered:
            answers = Answer.objects.filter(
                question_id=question, speaker_id=OuterRef("pk")
            )
            qs = qs.annotate(has_answer=Exists(answers)).filter(has_answer=False)
        return qs.order_by("id").distinct().order_by(Lower(speaker_name_expression()))

    def get_table_data(self):
        return self.get_queryset()

    @cached_property
    def short_questions(self):
        return questions_for_user(self.request.event, self.request.user).filter(
            target=QuestionTarget.SPEAKER, variant__in=QuestionVariant.short_answers
        )

    def get_table_kwargs(self):
        result = super().get_table_kwargs()
        result["has_arrived_permission"] = self.request.user.has_perm(
            "person.mark_arrived_speakerprofile", self.request.event
        )
        result["has_update_permission"] = self.request.user.has_perm(
            "person.update_speakerprofile", self.request.event
        )
        result["short_questions"] = list(self.short_questions)
        return result


class SpeakerCreate(EventPermissionRequired, FormView):
    template_name = "orga/speaker/create.html"
    form_class = AddSpeakerForm
    permission_required = "submission.orga_update_submission"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["standalone"] = True
        return kwargs

    def form_valid(self, form):
        if not form.has_speaker_data:
            return redirect(self.request.event.orga_urls.speakers)
        try:
            with transaction.atomic():
                speaker = form.create_speaker(user=self.request.user)
        except SendMailException as exception:
            form.add_error(None, str(exception))
            return self.form_invalid(form)
        messages.success(self.request, _("The speaker has been created."))
        return redirect(speaker.orga_urls.base)


class SpeakerViewMixin(PermissionRequired):
    def get_object(self):
        include_bare = self.request.user.has_perm(
            "submission.orga_update_submission", self.request.event
        )
        return get_object_or_404(
            speakers_for_user(
                self.request.event, self.request.user, include_bare=include_bare
            ),
            code__iexact=self.kwargs["code"],
        )

    @cached_property
    def object(self):
        return self.get_object()


class SpeakerDetail(SpeakerViewMixin, CreateOrUpdateView):
    template_name = "orga/speaker/form.html"
    form_class = SpeakerProfileForm
    extra_forms_signal = "pretalx.orga.signals.speaker_form"
    model = SpeakerProfile
    permission_required = "person.orga_list_speakerprofile"
    write_permission_required = "person.update_speakerprofile"

    def get_success_url(self) -> str:
        return self.object.orga_urls.base

    @context
    @cached_property
    def submissions(self, **kwargs):
        return submissions_for_user(self.request.event, self.request.user).filter(
            speakers=self.object
        )

    @context
    @cached_property
    def accepted_submissions(self, **kwargs):
        return self.submissions.filter(state__in=SubmissionStates.accepted_states)

    @cached_property
    def can_edit_speaker(self):
        return self.request.user.has_perm("person.update_speakerprofile", self.object)

    @cached_property
    def can_view_speaker_history(self):
        return self.request.user.has_perm(
            "person.update_speakerprofile", self.request.event
        )

    @context
    @cached_property
    def mails(self):
        if not self.can_view_speaker_history:
            return self.request.event.queued_mails.none()
        return (
            self.request.event.queued_mails.filter(to_speakers=self.object)
            .filter(state=QueuedMailStates.SENT)
            .distinct()
            .order_by("-sent")
        )

    @context
    @cached_property
    def questions_form(self):
        return QuestionsForm(
            self.request.POST if self.request.method == "POST" else None,
            files=self.request.FILES if self.request.method == "POST" else None,
            target="speaker",
            speaker=self.object,
            event=self.request.event,
            for_reviewers=(
                not self.request.user.has_perm(
                    "submission.orga_update_submission", self.request.event
                )
                and self.request.user.has_perm(
                    "submission.list_review", self.request.event
                )
            ),
        )

    @transaction.atomic()
    def form_valid(self, form):
        if not self.questions_form.is_valid():
            return self.get(self.request, *self.args, **self.kwargs)

        old_speaker = form.instance.__class__.objects.get(pk=form.instance.pk)
        old_data = old_speaker.get_instance_data()
        old_questions_data = self.questions_form.serialize_answers()

        # Save the form and show success message (skipping FormLoggingMixin's logging)
        result = super().form_valid(form, skip_logging=True)
        self.object = form.instance
        self.questions_form.save()

        messages.success(self.request, phrases.base.saved)

        if form.has_changed() or self.questions_form.has_changed():
            new_data = form.instance.get_instance_data()
            new_questions_data = self.questions_form.serialize_answers()
            form.instance.log_action(
                "pretalx.user.profile.update",
                person=self.request.user,
                orga=True,
                old_data=json_roundtrip(old_data | old_questions_data),
                new_data=json_roundtrip(new_data | new_questions_data),
            )

        return result

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            {
                "event": self.request.event,
                "instance": self.object,
                "is_orga": self.can_edit_speaker,
                "with_email": self.can_edit_speaker,
            }
        )
        return kwargs


class SpeakerPasswordReset(SpeakerViewMixin, ActionConfirmMixin, DetailView):
    permission_required = "person.update_speakerprofile"
    model = SpeakerProfile
    context_object_name = "speaker"
    action_confirm_icon = "key"
    action_confirm_label = phrases.base.password_reset_heading
    action_title = phrases.base.password_reset_heading
    action_text = phrases.base.password_reset_confirm

    def get_object(self):
        speaker = super().get_object()
        if not speaker.user:
            raise Http404
        return speaker

    def action_object_name(self):
        speaker = self.get_object()
        return f"{speaker.get_display_name()} ({speaker.user.email})"

    def action_back_url(self):
        return self.get_object().orga_urls.base

    def post(self, request, *args, **kwargs):
        speaker = self.get_object()
        try:
            reset_password(
                speaker.user,
                event=getattr(self.request, "event", None),
                log_actor=self.request.user,
                orga=False,
            )
            messages.success(self.request, phrases.orga.password_reset_success)
        except SendMailException:
            messages.error(self.request, phrases.orga.password_reset_fail)
        return redirect(speaker.orga_urls.base)


class SpeakerInvite(SpeakerViewMixin, FormView):
    permission_required = "person.update_speakerprofile"
    template_name = "orga/speaker/invite.html"
    form_class = SpeakerInviteForm

    def get_object(self):
        speaker = super().get_object()
        if speaker.user_id:
            raise Http404
        return speaker

    @context
    def speaker(self):
        return self.object

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["profile"] = self.object
        return kwargs

    def form_valid(self, form):
        try:
            send_speaker_invite(
                self.object,
                subject=form.cleaned_data["subject"],
                text=form.cleaned_data["text"],
                log_user=self.request.user,
            )
        except SendMailException as exception:
            form.add_error(None, str(exception))
            return self.form_invalid(form)
        messages.success(self.request, _("The invitation has been sent."))
        return redirect(self.object.orga_urls.base)


class SpeakerInviteRetract(SpeakerViewMixin, ActionConfirmMixin, DetailView):
    permission_required = "person.update_speakerprofile"
    model = SpeakerProfile
    context_object_name = "speaker"
    action_confirm_icon = "envelope"
    action_confirm_label = _("Retract invitation")
    action_title = _("Retract invitation")
    action_text = _(
        "Do you really want to retract this invitation? The link in the "
        "invitation mail will stop working."
    )

    def get_object(self):
        speaker = super().get_object()
        if not speaker.invitation_token:
            raise Http404
        return speaker

    def action_object_name(self):
        speaker = self.get_object()
        return f"{speaker.get_display_name()} ({speaker.effective_email})"

    def action_back_url(self):
        return self.get_object().orga_urls.base

    def post(self, request, *args, **kwargs):
        speaker = self.get_object()
        retract_speaker_invite(speaker, log_user=request.user)
        messages.success(request, _("The invitation has been retracted."))
        return redirect(speaker.orga_urls.base)


class SpeakerDelete(SpeakerViewMixin, ActionConfirmMixin, DetailView):
    permission_required = "person.delete_speakerprofile"
    model = SpeakerProfile
    context_object_name = "speaker"

    action_text = _(
        "Do you really want to delete this speaker profile? The profile and "
        "everything about it will be removed permanently, including all emails "
        "sent to this speaker. This action cannot be undone."
    )

    @property
    def action_object_name(self):
        speaker = self.object
        if email := speaker.effective_email:
            return f"{speaker.get_display_name()} ({email})"
        return speaker.get_display_name()

    @property
    def action_back_url(self):
        return self.object.orga_urls.base

    def post(self, request, *args, **kwargs):
        shred_speaker_profile(self.object, user=request.user)
        messages.success(request, _("The speaker profile has been deleted."))
        return redirect(request.event.orga_urls.speakers)


class SpeakerToggleArrived(SpeakerViewMixin, View):
    permission_required = "person.update_speakerprofile"

    @transaction.atomic
    def post(self, request, event, code):
        self.object.has_arrived = not self.object.has_arrived
        self.object.save()
        action = (
            "pretalx.speaker.arrived"
            if self.object.has_arrived
            else "pretalx.speaker.unarrived"
        )
        self.object.log_action(action, person=self.request.user, orga=True)
        if url := get_next_url(request):
            return redirect(url)
        return redirect(self.object.orga_urls.base)


class SpeakerSearch(EventPermissionRequired, View):
    """JSON autocomplete for the add-speaker form."""

    permission_required = "submission.orga_update_submission"

    def get(self, request, *args, **kwargs):
        search = request.GET.get("search")
        if not search or len(search) < 3:
            return JsonResponse({"count": 0, "results": []})

        profiles = speakers_for_user(
            request.event, request.user, include_bare=True
        ).filter(speaker_search_q(search))[:8]
        profile_entries = [
            {
                "code": profile.code,
                "name": profile.get_display_name(),
                "avatar": profile.get_avatar_url(thumbnail="tiny") or None,
                "managed": profile.is_managed,
                "has_email": bool(profile.effective_email),
            }
            for profile in profiles
        ]

        results = []
        if profile_entries:
            results.append(
                {
                    "type": "profile",
                    "label": _("Speakers in this event"),
                    "entries": profile_entries,
                }
            )
        return JsonResponse({"count": len(profile_entries), "results": results})


class SpeakerInformationView(OrgaCRUDView):
    model = SpeakerInformation
    form_class = SpeakerInformationForm
    table_class = SpeakerInformationTable
    template_namespace = "orga/speaker"
    context_object_name = "information"
    create_button_label = _("New speaker information")

    def get_queryset(self):
        return (
            self.request.event.information.all()
            .prefetch_related("limit_tracks", "limit_types")
            .order_by("pk")
        )

    def get_permission_required(self):
        permission_map = {"detail": "orga_detail"}
        permission = permission_map.get(self.action, self.action)
        return self.model.get_perm(permission)

    def get_generic_title(self, instance=None):
        if self.action != "list":
            return _("Speaker Information Note")
        return _("Speaker Information Notes")


class SpeakerExport(EventPermissionRequired, FormView):
    permission_required = "event.update_event"
    template_name = "orga/speaker/export.html"
    form_class = SpeakerExportForm

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["event"] = self.request.event
        return result

    @cached_property
    def schedule(self):
        return self.request.event.current_schedule or self.request.event.wip_schedule

    @context
    def exporters(self):
        return [
            exporter
            for exporter in get_schedule_exporters(self.request, schedule=self.schedule)
            if exporter.group == "speaker"
        ]

    @context
    def tablist(self):
        return {
            "custom": _("CSV/JSON exports"),
            "general": _("More exports"),
            "api": _("API"),
        }

    @context
    def api_buttons(self):
        return api_buttons(self.request.event)

    def form_valid(self, form):
        result = form.export_data()
        if not result:
            messages.warning(self.request, phrases.orga.no_data_to_export)
            return redirect(self.request.path)
        return result
