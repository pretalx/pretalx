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
from django.shortcuts import get_object_or_404, redirect, reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django.views.generic import (
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django_context_decorator import context

from pretalx.cfp.forms.submissions import SubmissionInvitationForm
from pretalx.cfp.views.event import LoggedInEventPageMixin
from pretalx.common.forms.fields import SizeFileInput
from pretalx.common.image import gravatar_csp
from pretalx.common.middleware.event import get_login_redirect
from pretalx.common.text.phrases import phrases
from pretalx.common.text.serialize import json_roundtrip
from pretalx.common.ui import Button, LinkButton, back_button, delete_button
from pretalx.common.views.helpers import is_form_bound
from pretalx.person.forms import (
    LoginInfoForm,
    SpeakerAvailabilityForm,
    SpeakerProfileForm,
)
from pretalx.person.rules import can_view_information
from pretalx.submission.forms import InfoForm, QuestionsForm, ResourceForm
from pretalx.submission.models import Resource, Submission, SubmissionStates


@method_decorator(gravatar_csp(), name="dispatch")
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
    def can_edit_profile(self):
        return self.request.event.get_feature_flag("speakers_can_edit_submissions")

    @context
    @cached_property
    def profile_form(self):
        bind = is_form_bound(self.request, "profile")
        return SpeakerProfileForm(
            user=self.request.user,
            event=self.request.event,
            read_only=not self.can_edit_profile,
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
            speaker=self.request.user,
            readonly=not self.can_edit_profile,
            event=self.request.event,
            target="speaker",
        )

    @context
    def questions_exist(self):
        return self.request.event.questions.filter(target="speaker").exists()

    def post(self, request, *args, **kwargs):
        if self.login_form.is_bound and self.login_form.is_valid():
            self.login_form.save()
            request.user.log_action("pretalx.user.password.update")
        elif self.profile_form.is_bound and self.profile_form.is_valid():
            profile = self.request.user.event_profile(self.request.event)
            old_profile_data = profile._get_instance_data()
            self.profile_form.save()
            if self.profile_form.has_changed():
                new_profile_data = self.profile_form.instance._get_instance_data()
                profile.log_action(
                    "pretalx.user.profile.update",
                    person=request.user,
                    old_data=old_profile_data,
                    new_data=new_profile_data,
                )
                self.request.event.cache.set("rebuild_schedule_export", True, None)
        elif self.questions_form.is_bound and self.questions_form.is_valid():
            profile = self.request.user.event_profile(self.request.event)
            old_questions_data = self.questions_form.serialize_answers()
            self.questions_form.save()
            if self.questions_form.has_changed():
                new_questions_data = self.questions_form.serialize_answers()
                profile.log_action(
                    "pretalx.user.profile.update",
                    person=request.user,
                    old_data=old_questions_data,
                    new_data=new_questions_data,
                )
                self.request.event.cache.set("rebuild_schedule_export", True, None)
        else:
            return super().get(request, *args, **kwargs)

        messages.success(self.request, phrases.base.saved)
        return redirect("cfp:event.user.view", event=self.request.event.slug)


class SubmissionViewMixin:
    permission_required = "submission.update_submission"

    def has_permission(self):
        return super().has_permission() or self.request.user.has_perm(
            "submission.orga_list_submission", self.request.event
        )

    def dispatch(self, request, *args, **kwargs):
        if self.request.user not in self.object.speakers.all():
            # User has permission to see permission, but not to see this particular
            # page, so we redirect them to the organiser page
            return redirect(self.object.orga_urls.base)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):

        return get_object_or_404(
            Submission.all_objects.filter(event=self.request.event)
            .exclude(state=SubmissionStates.DELETED)
            .prefetch_related("answers", "answers__options", "speakers"),
            code__iexact=self.kwargs["code"],
        )

    @context
    @cached_property
    def object(self):
        return self.get_object()

    @context
    @cached_property
    def submission(self, **kwargs):
        return self.get_object()


class SubmissionsListView(LoggedInEventPageMixin, ListView):
    template_name = "cfp/event/user_submissions.html"
    context_object_name = "submissions"

    @context
    def information(self):
        return [
            info
            for info in self.request.event.information.all()
            if can_view_information(self.request.user, info)
        ]

    @context
    def drafts(self):
        return Submission.all_objects.filter(
            event=self.request.event,
            speakers__in=[self.request.user],
            state=SubmissionStates.DRAFT,
        )

    def get_queryset(self):
        return self.request.event.submissions.filter(speakers__in=[self.request.user])


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
            if obj.state == SubmissionStates.ACCEPTED:
                with override(obj.event.locale):
                    obj.event.send_orga_mail(
                        str(
                            _(
                                textwrap.dedent(
                                    """
                        Hi,

                        this is your content system at {event_dashboard}.
                        Your accepted talk “{title}” by {speakers} was just withdrawn by {user}.
                        You can find details at {url}.

                        Best regards,
                        pretalx
                        """
                                )
                            )
                        ).format(
                            title=obj.title,
                            speakers=obj.display_speaker_names,
                            user=request.user.get_display_name(),
                            event_dashboard=request.event.orga_urls.base.full(),
                            url=obj.orga_urls.edit.full(),
                        )
                    )
            obj.withdraw(person=request.user)
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
            self.template_name = "cfp/event/user_submission_confirm_error.html"
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def speaker_profile(self):
        return self.request.user.event_profile(self.request.event)

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["speaker_profile"] = self.speaker_profile
        result["event"] = self.request.event
        return result

    def get_form(self):
        form = super().get_form()
        if not self.request.event.cfp.request_availabilities:
            form.fields.pop("availabilities")
        else:
            form.fields["availabilities"].required = (
                self.request.event.cfp.require_availabilities
            )
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons"] = [Button(label=_("Confirm"))]
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
            submission.confirm(person=self.request.user)
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
            raise Http404()
        return submission

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_buttons"] = [delete_button()]
        context["submit_buttons_extra"] = [back_button(self.submission.urls.user_base)]
        return context

    def post(self, request, *args, **kwargs):
        self.submission.delete()
        messages.success(self.request, _("Your draft was discarded."))
        return redirect("cfp:event.user.submissions", event=self.request.event.slug)


class SubmissionsEditView(LoggedInEventPageMixin, SubmissionViewMixin, UpdateView):
    template_name = "cfp/event/user_submission_edit.html"
    model = Submission
    form_class = InfoForm
    context_object_name = "submission"
    permission_required = "submission.view_submission"
    write_permission_required = "submission.update_submission"

    def get_permission_object(self):
        return self.object

    @context
    def size_warning(self):
        return SizeFileInput.get_size_warning()

    @context
    @cached_property
    def formset(self):
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
        if not self.formset.is_valid():
            return False

        for form in self.formset.initial_forms:
            if form in self.formset.deleted_forms:
                if not form.instance.pk:
                    continue
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.instance.submission = obj
                form.save()

        extra_forms = [
            form
            for form in self.formset.extra_forms
            if form.has_changed
            and not self.formset._should_delete_form(form)
            and form.is_valid()
        ]
        for form in extra_forms:
            form.instance.submission = obj
            form.save()

        return True

    @context
    @cached_property
    def qform(self):
        return QuestionsForm(
            data=self.request.POST if self.request.method == "POST" else None,
            files=self.request.FILES if self.request.method == "POST" else None,
            submission=self.object,
            target="submission",
            event=self.request.event,
            readonly=not self.can_edit,
        )

    @cached_property
    def object(self):
        return self.get_object()

    def post(self, request, *args, **kwargs):
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
        kwargs["readonly"] = not self.can_edit
        # At this stage, new speakers can be added via the dedicated form
        kwargs["remove_additional_speaker"] = True
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        if not self.can_edit:
            messages.error(self.request, phrases.cfp.submission_uneditable)
            return redirect(self.object.urls.user_base)

        old_submission_data = {}
        old_questions_data = {}
        model_class = form.instance.__class__
        manager = model_class.all_objects or model_class.objects
        old_submission = manager.filter(pk=form.instance.pk).first()
        if old_submission:
            old_submission_data = old_submission._get_instance_data() or {}
            old_questions_data = self.qform.serialize_answers() or {}

        form.save()
        self.qform.save()

        if not self.save_formset(form.instance):  # validation failed
            return self.get(self.request, *self.args, **self.kwargs)

        if (
            form.instance.state != SubmissionStates.DRAFT
            and form.instance.pk
            and (
                form.has_changed()
                or self.qform.has_changed()
                or self.formset.has_changed()
            )
        ):
            if "duration" in form.changed_data:
                form.instance.update_duration()
            if "track" in form.changed_data:
                form.instance.update_review_scores()
            new_submission_data = form.instance._get_instance_data() or {}
            new_questions_data = self.qform.serialize_answers() or {}
            form.instance.log_action(
                "pretalx.submission.update",
                person=self.request.user,
                old_data=json_roundtrip(old_submission_data | old_questions_data),
                new_data=json_roundtrip(new_submission_data | new_questions_data),
            )
            self.request.event.cache.set("rebuild_schedule_export", True, None)

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
            request.user.deactivate()
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
        kwargs["speaker"] = self.request.user
        if "email" in self.request.GET and self.request.method != "POST":
            initial = kwargs.get("initial", {})
            initial["speaker"] = urllib.parse.unquote(self.request.GET["email"])
            kwargs["initial"] = initial

            try:
                validate_email(initial["speaker"])
            except ValidationError:
                messages.warning(self.request, phrases.cfp.invite_invalid_email)
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, phrases.cfp.invite_sent)
        self.submission.log_action(
            "pretalx.submission.speakers.invite", person=self.request.user
        )
        return super().form_valid(form)

    def get_success_url(self):
        return self.submission.urls.user_base


class SubmissionInviteAcceptView(LoggedInEventPageMixin, DetailView):
    template_name = "cfp/event/invitation.html"
    context_object_name = "submission"

    def get_object(self, queryset=None):
        return get_object_or_404(
            Submission,
            code__iexact=self.kwargs["code"],
            invitation_token__iexact=self.kwargs["invitation"],
        )

    @context
    @cached_property
    def can_accept_invite(self):
        return self.request.user.has_perm(
            "submission.add_speaker_submission", self.get_object()
        )

    def post(self, request, *args, **kwargs):
        if not self.can_accept_invite:
            messages.error(self.request, _("You cannot accept this invitation."))
            return redirect(self.request.event.urls.user)
        submission = self.get_object()
        submission.speakers.add(self.request.user)
        submission.log_action(
            "pretalx.submission.speakers.add", person=self.request.user
        )
        submission.save()
        messages.success(self.request, phrases.cfp.invite_accepted)
        return redirect("cfp:event.user.view", event=self.request.event.slug)


class MailListView(LoggedInEventPageMixin, TemplateView):
    template_name = "cfp/event/user_mails.html"

    @context
    def mails(self):
        return self.request.user.mails.filter(sent__isnull=False).order_by("-sent")
