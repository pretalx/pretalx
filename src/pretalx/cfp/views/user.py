# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import textwrap
import urllib

from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.forms.models import BaseModelFormSet, inlineformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override, pgettext_lazy
from django.views.generic import (
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django_context_decorator import context
from django_tables2 import RequestConfig

from pretalx.cfp.views.event import LoggedInEventPageMixin
from pretalx.common.exceptions import SubmissionError
from pretalx.common.forms import save_related_formset
from pretalx.common.forms.fields import SizeFileInput
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import json_roundtrip
from pretalx.common.ui import Button, LinkButton, back_button, delete_button
from pretalx.common.views.helpers import get_htmx_target, is_form_bound, is_htmx
from pretalx.common.views.redirect import get_login_redirect
from pretalx.event.domain.mail import send_orga_mail
from pretalx.mail.enums import QueuedMailStates
from pretalx.person.domain.user import deactivate_user
from pretalx.person.interfaces.forms import (
    LoginInfoForm,
    SpeakerAvailabilityForm,
    SpeakerProfileForm,
    SubmissionInvitationForm,
)
from pretalx.submission.domain.invitation import (
    accept_invitation,
    retract_invitation,
    send_invitation,
)
from pretalx.submission.domain.queries.submission import information_for_user
from pretalx.submission.domain.submission import apply_field_changes, delete_submission
from pretalx.submission.interfaces.forms import (
    QuestionsForm,
    ResourceForm,
    SubmissionInfoForm,
)
from pretalx.submission.interfaces.tables import AttendeeSignupTable
from pretalx.submission.models import (
    Resource,
    Submission,
    SubmissionInvitation,
    SubmissionStates,
)
from pretalx.submission.validators.speaker import DEFAULT_MAX_SPEAKERS


class ProfileView(LoggedInEventPageMixin, TemplateView):
    template_name = "cfp/event/user_profile.html"

    @context
    @cached_property
    def login_form(self):
        return LoginInfoForm(
            user=self.request.user,
            data=self.request.POST if is_form_bound(self.request, "login") else None,
        )

    @cached_property
    def can_edit_speaker(self):
        return self.request.event.get_feature_flag("speakers_can_edit_submissions")

    @context
    @cached_property
    def profile_form(self):
        bind = is_form_bound(self.request, "profile")
        return SpeakerProfileForm(
            user=self.request.user,
            event=self.request.event,
            read_only=not self.can_edit_speaker,
            with_email=False,
            field_configuration=self.request.event.cfp_flow.config.get(
                "profile", {}
            ).get("fields"),
            data=self.request.POST if bind else None,
            files=self.request.FILES if bind else None,
        )

    @context
    @cached_property
    def questions_form(self):
        bind = is_form_bound(self.request, "questions")
        return QuestionsForm(
            data=self.request.POST if bind else None,
            files=self.request.FILES if bind else None,
            speaker=self.request.user.get_speaker(self.request.event),
            read_only=not self.can_edit_speaker,
            event=self.request.event,
            target="speaker",
        )

    @context
    def questions_exist(self):
        return self.request.event.questions.filter(target="speaker").exists()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if self.login_form.is_bound and self.login_form.is_valid():
            self.login_form.save()
        elif self.profile_form.is_bound and self.profile_form.is_valid():
            speaker = self.request.user.get_speaker(self.request.event)
            old_data = speaker.get_instance_data()
            self.profile_form.save()
            if self.profile_form.has_changed():
                new_data = self.profile_form.instance.get_instance_data()
                speaker.log_action(
                    "pretalx.user.profile.update",
                    person=request.user,
                    old_data=old_data,
                    new_data=new_data,
                )
        elif self.questions_form.is_bound and self.questions_form.is_valid():
            speaker = self.request.user.get_speaker(self.request.event)
            old_questions_data = self.questions_form.serialize_answers()
            self.questions_form.save()
            if self.questions_form.has_changed():
                new_questions_data = self.questions_form.serialize_answers()
                speaker.log_action(
                    "pretalx.user.profile.update",
                    person=request.user,
                    old_data=old_questions_data,
                    new_data=new_questions_data,
                )
        else:
            return super().get(request, *args, **kwargs)

        messages.success(self.request, phrases.base.saved)
        return redirect("cfp:event.user.view", event=self.request.event.slug)


class SubmissionViewMixin:
    permission_required = "submission.update_submission"

    def dispatch(self, request, *args, **kwargs):
        if not self.object.speakers.filter(user=self.request.user).exists():
            # This user has the permission to see the submission in general, but is not
            # a speaker; most likely this is an organiser who clicked an email contained
            # in a speaker email. We redirect them to the organiser page instead.
            return redirect(self.object.orga_urls.base)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):
        return get_object_or_404(
            Submission.all_objects.filter(event=self.request.event).prefetch_related(
                "answers", "answers__options", "speakers"
            ),
            code__iexact=self.kwargs["code"],
        )

    @context
    @cached_property
    def submission(self, **kwargs):
        return self.get_object()


class SubmissionsListView(LoggedInEventPageMixin, ListView):
    template_name = "cfp/event/user_submissions.html"
    context_object_name = "submissions"

    @context
    def information(self):
        return information_for_user(self.request.event, self.request.user)

    @context
    def drafts(self):
        return Submission.all_objects.filter(
            event=self.request.event,
            speakers__user=self.request.user,
            state=SubmissionStates.DRAFT,
        ).select_related("event")

    def get_queryset(self):
        return self.request.event.submissions.filter(
            speakers__user=self.request.user
        ).select_related("submission_type")


class SubmissionsWithdrawView(LoggedInEventPageMixin, SubmissionViewMixin, DetailView):
    template_name = "cfp/event/user_submission_withdraw.html"
    model = Submission
    context_object_name = "submission"
    permission_required = "submission.is_speaker_submission"

    def get_permission_object(self):
        return self.get_object()

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if self.request.user.has_perm("submission.withdraw_submission", obj):
            was_accepted = obj.state == SubmissionStates.ACCEPTED
            try:
                obj.withdraw(person=request.user)
            except SubmissionError as e:
                messages.error(self.request, str(e))
                return redirect(
                    "cfp:event.user.submissions", event=self.request.event.slug
                )
            if was_accepted:
                with override(obj.event.locale):
                    withdraw_text = str(
                        _(
                            textwrap.dedent("""
                        Hi,

                        this is your content system at {event_dashboard}.
                        Your accepted talk “{proposal_title}” by {speakers} was just withdrawn by {name}.
                        You can find details at {url}.

                        Best regards,
                        pretalx
                        """)
                        )
                    )
                    send_orga_mail(
                        obj.event,
                        withdraw_text,
                        safe_extra_context={"url": obj.orga_urls.edit},
                        submission=obj,
                        user=request.user,
                    )
            messages.success(self.request, phrases.cfp.submission_withdrawn)
        else:
            messages.error(self.request, phrases.cfp.submission_not_withdrawn)
        return redirect("cfp:event.user.submissions", event=self.request.event.slug)


class SubmissionConfirmView(LoggedInEventPageMixin, SubmissionViewMixin, FormView):
    template_name = "cfp/event/user_submission_confirm.html"
    form_class = SpeakerAvailabilityForm

    def get_object(self):
        return get_object_or_404(
            self.request.event.submissions, code__iexact=self.kwargs.get("code")
        )

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return get_login_redirect(request)
        if not request.user.has_perm(
            "submission.is_speaker_submission", self.submission
        ):
            return render(request, "cfp/event/user_submission_confirm_error.html", {})
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def speaker(self):
        return self.request.user.get_speaker(self.request.event)

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["speaker"] = self.speaker
        result["event"] = self.request.event
        return result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons"] = [
            Button(label=pgettext_lazy("action: confirm attendance", "Confirm"))
        ]
        context["submit_buttons_extra"] = [
            back_button(self.submission.urls.user_base),
            LinkButton(
                href=self.submission.urls.withdraw,
                color="danger",
                icon=None,
                label=_("Withdraw"),
            ),
        ]
        return context

    def form_valid(self, form):
        submission = self.submission
        form.save()
        if self.request.user.has_perm("submission.confirm_submission", submission):
            try:
                submission.confirm(person=self.request.user)
            except SubmissionError as e:
                messages.error(self.request, str(e))
                return redirect(
                    "cfp:event.user.submissions", event=self.request.event.slug
                )
            messages.success(self.request, phrases.cfp.submission_confirmed)
        elif submission.state == SubmissionStates.CONFIRMED:
            messages.success(self.request, phrases.cfp.submission_was_confirmed)
        else:
            messages.error(self.request, phrases.cfp.submission_not_confirmed)
        return redirect("cfp:event.user.submissions", event=self.request.event.slug)


class SubmissionDraftDiscardView(
    LoggedInEventPageMixin, SubmissionViewMixin, TemplateView
):
    template_name = "cfp/event/user_submission_discard.html"
    form_class = SpeakerAvailabilityForm

    def get_object(self):
        submission = super().get_object()
        if submission.state != SubmissionStates.DRAFT:
            raise Http404
        return submission

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons"] = [delete_button()]
        context["submit_buttons_extra"] = [back_button(self.submission.urls.user_base)]
        return context

    def post(self, request, *args, **kwargs):
        delete_submission(self.submission, person=request.user, orga=False)
        messages.success(self.request, _("Your draft was discarded."))
        return redirect("cfp:event.user.submissions", event=self.request.event.slug)


class SubmissionsEditView(LoggedInEventPageMixin, SubmissionViewMixin, UpdateView):
    template_name = "cfp/event/user_submission_edit.html"
    model = Submission
    form_class = SubmissionInfoForm
    context_object_name = "submission"
    permission_required = "submission.view_submission"
    write_permission_required = "submission.update_submission"

    def get_permission_object(self):
        return self.object

    @context
    def size_warning(self):
        return SizeFileInput.get_size_warning()

    @cached_property
    def _resources_enabled(self):
        return self.request.event.cfp.request_resources

    @context
    def resources_enabled(self):
        return self._resources_enabled

    @context
    @cached_property
    def formset(self):
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
        submission = self.object
        return formset_class(
            self.request.POST if self.request.method == "POST" else None,
            files=self.request.FILES if self.request.method == "POST" else None,
            queryset=(
                submission.resources.all() if submission else Resource.objects.none()
            ),
            prefix="resource",
        )

    def save_formset(self, obj):
        if not self.formset:
            return
        save_related_formset(self.formset, parent=obj, fk_field="submission")

    @context
    @cached_property
    def qform(self):
        return QuestionsForm(
            data=self.request.POST if self.request.method == "POST" else None,
            files=self.request.FILES if self.request.method == "POST" else None,
            submission=self.object,
            target="submission",
            event=self.request.event,
            read_only=not self.can_edit,
        )

    @context
    @cached_property
    def invitations(self):
        return self.object.invitations.all()

    @context
    @cached_property
    def can_add_more_speakers(self):
        max_speakers = self.request.event.cfp.max_speakers
        if max_speakers is None:
            max_speakers = DEFAULT_MAX_SPEAKERS
        current_count = self.object.speakers.count() + len(self.invitations)
        return current_count < max_speakers

    @cached_property
    def object(self):
        return self.get_object()

    @context
    @cached_property
    def signup_enabled(self):
        return (
            self.request.event.get_feature_flag("attendee_signup")
            and self.object.requires_signup
            and self.object.state in SubmissionStates.accepted_states
        )

    @context
    @cached_property
    def signup_attendee_count(self):
        if not self.signup_enabled:
            return None
        return self.object.confirmed_signup_count

    @context
    @cached_property
    def signup_capacity(self):
        if not self.signup_enabled:
            return None
        return self.object.effective_signup_capacity

    @context
    @cached_property
    def signup_capacity_percent(self):
        if not self.signup_enabled:
            return None
        return self.object.signup_capacity_percent

    @context
    @cached_property
    def signup_table(self):
        if not self.signup_enabled:
            return None
        queryset = self.object.attendee_signups.select_related(
            "attendee", "attendee__user"
        ).order_by("-state", "position", "id")
        table = AttendeeSignupTable(data=queryset)
        RequestConfig(self.request, paginate=False).configure(table)
        if not len(table.rows):
            return None
        return table

    def get(self, request, *args, **kwargs):
        if is_htmx(request) and get_htmx_target(request).startswith("table-content"):
            self.object = self.get_object()
            response = render(
                request,
                "common/includes/table.html#table-content",
                {"table": self.signup_table},
            )
            response["HX-Push-Url"] = request.get_full_path()
            return response
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not self.can_edit:
            messages.error(self.request, phrases.cfp.submission_uneditable)
            return redirect(self.object.urls.user_base)
        form = self.get_form()
        if form.is_valid() and self.qform.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    @context
    @cached_property
    def can_edit(self):
        return self.object.editable

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["field_configuration"] = (
            self.request.event.cfp_flow.config.get("steps", {})
            .get("info", {})
            .get("fields")
        )
        kwargs["read_only"] = not self.can_edit
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        if self.formset and not self.formset.is_valid():
            return self.get(self.request, *self.args, **self.kwargs)

        old_submission_data = {}
        old_questions_data = {}
        model_class = form.instance.__class__
        manager = model_class.all_objects or model_class.objects
        old_submission = manager.get(pk=form.instance.pk)
        old_submission_data = old_submission.get_instance_data() or {}
        old_questions_data = self.qform.serialize_answers() or {}

        form.save()
        self.qform.save()
        self.save_formset(form.instance)

        if (
            form.instance.state != SubmissionStates.DRAFT
            and not form.instance._state.adding
            and (
                form.has_changed()
                or self.qform.has_changed()
                or (self.formset and self.formset.has_changed())
            )
        ):
            apply_field_changes(form.instance, form.changed_data)
            new_submission_data = form.instance.get_instance_data() or {}
            new_questions_data = self.qform.serialize_answers() or {}
            form.instance.log_action(
                "pretalx.submission.update",
                person=self.request.user,
                old_data=json_roundtrip(old_submission_data | old_questions_data),
                new_data=json_roundtrip(new_submission_data | new_questions_data),
            )
        elif (
            form.instance.state == SubmissionStates.DRAFT
            and self.request.POST.get("action", "submit") == "dedraft"
        ):
            url = reverse(
                "cfp:event.cfp.restart",
                kwargs={"event": self.request.event.slug, "code": form.instance.code},
            )
            if form.instance.access_code:
                url += f"?access_code={form.instance.access_code.code}"
            return redirect(url)
        messages.success(self.request, phrases.base.saved)
        return redirect(self.object.urls.user_base)


class DeleteAccountView(LoggedInEventPageMixin, View):
    @staticmethod
    def post(request, event):
        if request.POST.get("really"):
            deactivate_user(request.user)
            logout(request)
            messages.success(request, _("Your account has now been deleted."))
            return redirect(request.event.urls.base)
        messages.error(request, _("Are you really sure? Please tick the box"))
        return redirect(request.event.urls.user + "?really")


class SubmissionInviteView(LoggedInEventPageMixin, SubmissionViewMixin, FormView):
    form_class = SubmissionInvitationForm
    template_name = "cfp/event/user_submission_invitation.html"
    permission_required = "submission.add_speaker_submission"

    def get_permission_object(self):
        return self.get_object()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["submission"] = self.submission
        if "email" in self.request.GET and self.request.method != "POST":
            initial = kwargs.get("initial", {})
            initial["speaker"] = urllib.parse.unquote(self.request.GET["email"])
            kwargs["initial"] = initial

            try:
                validate_email(initial["speaker"])
            except ValidationError:
                messages.warning(self.request, phrases.cfp.invite_invalid_email)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        send_invitation(
            self.submission,
            email=form.cleaned_data["speaker"],
            sender=self.request.user,
        )
        messages.success(self.request, phrases.cfp.invite_sent)
        return super().form_valid(form)

    def get_success_url(self):
        return self.submission.urls.user_base


class SubmissionInviteRetractView(LoggedInEventPageMixin, SubmissionViewMixin, View):
    permission_required = "submission.add_speaker_submission"

    def get_permission_object(self):
        return self.get_object()

    def get_invitation(self):
        invitation_id = self.request.GET.get("id") or self.request.POST.get("id")
        return get_object_or_404(
            SubmissionInvitation, pk=invitation_id, submission=self.submission
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        invitation = self.get_invitation()
        retract_invitation(invitation, person=self.request.user)
        messages.success(self.request, _("The invitation has been retracted."))
        return redirect(self.submission.urls.user_base)


class SubmissionInviteAcceptView(LoggedInEventPageMixin, DetailView):
    template_name = "cfp/event/invitation.html"
    context_object_name = "submission"

    def get_invitation(self):
        return get_object_or_404(
            SubmissionInvitation,
            submission__code__iexact=self.kwargs["code"],
            submission__event=self.request.event,
            token__iexact=self.kwargs["invitation"],
        )

    def get_object(self, queryset=None):
        return self.invitation.submission

    @context
    @cached_property
    def invitation(self):
        return self.get_invitation()

    @context
    @cached_property
    def can_accept_invite(self):
        return self.request.user.has_perm(
            "submission.add_speaker_submission", self.get_object()
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if not self.can_accept_invite:
            messages.error(self.request, _("You cannot accept this invitation."))
            return redirect(self.request.event.urls.user)
        accept_invitation(self.invitation, user=self.request.user)
        messages.success(self.request, phrases.cfp.invite_accepted)
        return redirect("cfp:event.user.view", event=self.request.event.slug)


class MailListView(LoggedInEventPageMixin, TemplateView):
    template_name = "cfp/event/user_mails.html"

    @context
    def mails(self):
        return self.request.user.mails.filter(state=QueuedMailStates.SENT).order_by(
            "-sent"
        )
