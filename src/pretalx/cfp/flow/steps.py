# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Jahongir
# SPDX-FileContributor: Laura Klünder

import copy
from contextlib import suppress

from django.contrib import messages
from django.contrib.auth import login
from django.forms import ValidationError
from django.forms.models import modelformset_factory
from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.cfp.flow.base import DedraftMixin, FormFlowStep
from pretalx.common.text.phrases import phrases
from pretalx.person.interfaces.forms import SpeakerProfileForm, UserForm
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.domain.queries.question import active_questions
from pretalx.submission.domain.submission import (
    apply_invite_addresses,
    create_submission,
    submit_draft,
)
from pretalx.submission.interfaces.forms import InfoForm, QuestionsForm, ResourceForm
from pretalx.submission.models import Resource, SubmissionStates, SubmissionType, Track
from pretalx.submission.models.submission import Submission


class InfoStep(DedraftMixin, FormFlowStep):
    identifier = "info"
    icon = "paper-plane"
    form_class = InfoForm
    template_name = "cfp/event/submission_info.html"
    priority = 0
    field_keys = [
        "title",
        "submission_type",
        "abstract",
        "description",
        "notes",
        "do_not_record",
        "image",
        "track",
        "duration",
        "content_locale",
        "additional_speaker",
        "tags",
        "resources",
    ]
    always_required_fields = {"title", "submission_type"}
    label_model = Submission

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["access_code"] = getattr(self.request, "access_code", None)
        return result

    def get_form_initial(self):
        result = super().get_form_initial()
        for field, model in (("submission_type", SubmissionType), ("track", Track)):
            request_value = self.request.GET.get(field)
            if request_value:
                with suppress(AttributeError, ValueError, TypeError):
                    pk = int(request_value.split("-")[0])
                    obj = model.objects.filter(event=self.request.event, pk=pk).first()
                    if obj:
                        result[field] = obj
        return result

    def get_form_data(self):
        result = super().get_form_data()
        if "additional_speaker" in result and isinstance(
            result["additional_speaker"], list
        ):
            result["additional_speaker"] = ",".join(result["additional_speaker"])
        return result

    @cached_property
    def _resources_enabled(self):
        return self.event.cfp.request_resources

    @cached_property
    def _resources_required(self):
        return self.event.cfp.require_resources

    def _formset_has_resources(self, formset):
        return any(
            not f.cleaned_data.get("DELETE") for f in formset.forms if f.cleaned_data
        )

    def _get_stored_resource_files(self):
        stored_files = self.get_files() or {}
        return {
            key: value
            for key, value in stored_files.items()
            if key.startswith("resource-")
        }

    def get_resource_formset(self, submission, from_storage=False):
        if not self._resources_enabled:
            return None
        queryset = submission.resources.all() if submission else Resource.objects.none()
        formset_class = modelformset_factory(
            Resource, form=ResourceForm, can_delete=True, extra=0
        )
        if self.request.method == "POST" and not from_storage:
            # Merge stored session files for resources that weren't re-uploaded
            files = self.request.FILES.copy()
            for key, value in self._get_stored_resource_files().items():
                if key not in files:
                    files[key] = value
            return formset_class(
                data=self.request.POST,
                files=files,
                queryset=queryset,
                prefix="resource",
            )
        stored = self.cfp_session.get("data", {}).get("info__resources", {})
        if stored:
            data = QueryDict(mutable=True)
            data.update(stored)
            return formset_class(
                data=data, files=self.get_files(), queryset=queryset, prefix="resource"
            )
        return formset_class(queryset=queryset, prefix="resource")

    @cached_property
    def resource_formset(self):
        return self.get_resource_formset(submission=self.dedraft_submission)

    def is_valid(self):
        form_valid = super().is_valid()
        if not self._resources_enabled:
            return form_valid
        formset = self.resource_formset
        formset_valid = formset.is_valid()
        self.cfp_session["data"]["info__resources"] = {
            key: value
            for key, value in self.request.POST.items()
            if key.startswith("resource-")
        }
        resource_files = {
            key: value
            for key, value in self.request.FILES.items()
            if key.startswith("resource-")
        }
        if resource_files:
            try:
                self.set_files(resource_files)
            except ValidationError as e:
                messages.error(self.request, e.message)
                formset_valid = False
        if (
            formset_valid
            and self._resources_required
            and not self._formset_has_resources(formset)
        ):
            messages.error(self.request, _("Please add at least one resource."))
            formset_valid = False
        return form_valid and formset_valid

    def is_completed(self, request):
        self.request = request
        if not self.get_form(from_storage=True).is_valid():
            return False
        if self._resources_required:
            formset = self.get_resource_formset(
                submission=self.dedraft_submission, from_storage=True
            )
            if not formset or not formset.is_valid():
                return False
            if not self._formset_has_resources(formset):
                return False
        return True

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        formset = self.resource_formset
        if formset:
            stored_files = self._get_stored_resource_files()
            for form in formset.forms:
                file_key = f"{form.prefix}-resource"
                stored = stored_files.get(file_key)
                form.stored_filename = stored.name if stored else None
        result["resource_formset"] = formset
        result["resources_enabled"] = self._resources_enabled
        if self._resources_enabled:
            result["force_multipart"] = True
        return result

    def done(self, request, draft=False):
        self.request = request
        form = self.get_form(from_storage=True)
        form.is_valid()

        if access_code := getattr(request, "access_code", None):
            # Access code redemption is deferred to ``create_submission`` /
            # ``submit_draft`` so drafts do not consume codes.
            form.instance.access_code = access_code

        if form.instance._state.adding:
            # New proposal or new draft.
            form.instance.event = self.event
            form.instance.state = (
                SubmissionStates.DRAFT if draft else SubmissionStates.SUBMITTED
            )
            form.save(commit=False)  # Apply default values
            submission = create_submission(
                submission=form.instance,
                user=request.user,
                speakers=[request.user],
                tags=form.cleaned_data.get("tags") or (),
                invite_addresses=form.cleaned_data.get("additional_speaker"),
                send_initial_mails=not draft,
            )
        else:
            submission = form.save()
            emails = form.cleaned_data.get("additional_speaker") or []
            if not draft and submission.state == SubmissionStates.DRAFT:
                submit_draft(submission, user=request.user, invite_addresses=emails)
            else:
                apply_invite_addresses(submission, emails, sender=request.user)

        if self._resources_enabled:
            formset = self.get_resource_formset(
                submission=submission, from_storage=True
            )
            if formset and formset.is_valid():
                for resource_form in formset.forms:
                    if resource_form.cleaned_data.get("DELETE"):
                        if resource_form.instance.pk:
                            resource_form.instance.delete()
                    elif resource_form.has_changed():
                        # Existing resources arrive bound to their pk via the
                        # hidden id field, so save() updates in place; new
                        # resources need the submission attached first.
                        resource = resource_form.save(commit=False)
                        resource.submission = submission
                        resource.save()

        if draft:
            messages.success(
                self.request,
                _(
                    "Your draft was saved. You can continue to edit it as long as the CfP is open."
                ),
            )
        else:
            messages.success(
                self.request,
                _(
                    "Congratulations, you’ve submitted your proposal! You can continue to make changes to it "
                    "up to the submission deadline, and you will be notified of any changes or questions."
                ),
            )

        request.submission = submission

    @property
    def label(self):
        return phrases.base.general

    @property
    def _title(self):
        return _("Hey, nice to meet you!")

    @property
    def _text(self):
        return _(
            "We’re glad that you want to contribute to our event with your proposal. Let’s get started, this won’t take long."
        )


class QuestionsStep(DedraftMixin, FormFlowStep):
    identifier = "questions"
    icon = "question-circle-o"
    form_class = QuestionsForm
    template_name = "cfp/event/submission_questions.html"
    priority = 25
    dedraft_key = "submission"

    def is_applicable(self, request):
        self.request = request
        info_data = self.cfp_session.get("data", {}).get("info", {})
        return active_questions(
            self.event,
            target=None,
            track=info_data.get("track"),
            submission_type=info_data.get("submission_type"),
        ).exists()

    def get_extra_form_kwargs(self):
        return {"target": ""}

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        info_data = self.cfp_session.get("data", {}).get("info", {})
        result["track"] = info_data.get("track")
        access_code = getattr(self.request, "access_code", None)
        access_code_type = access_code.submission_types.first() if access_code else None
        if access_code_type:
            result["submission_type"] = access_code_type
        else:
            result["submission_type"] = info_data.get("submission_type")
        if not self.request.user.is_anonymous:
            result["speaker"] = self.request.user.get_speaker(self.request.event)
        if hasattr(self.request, "submission"):
            result.setdefault("submission", self.request.submission)
        return result

    def done(self, request, draft=False):
        form = self.get_form(from_storage=True)
        form.is_valid()
        form.save(
            submission=request.submission,
            speaker=request.user.get_speaker(request.event),
        )

    @property
    def label(self):
        return _("Additional information")

    @property
    def _title(self):
        return _("Tell us more!")

    @property
    def _text(self):
        return _(
            "Before we can save your proposal, we have some more questions for you."
        )


class UserStep(FormFlowStep):
    identifier = "user"
    icon = "user-circle-o"
    form_class = UserForm
    template_name = "cfp/event/submission_user.html"
    priority = 49

    def is_applicable(self, request):
        return not request.user.is_authenticated

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["request"] = self.request
        result["no_buttons"] = True
        result["success_url"] = self.get_next_url(self.request)
        return result

    def done(self, request, draft=False):
        if not getattr(request.user, "is_authenticated", False):
            form = self.get_form(from_storage=True)
            form.is_valid()
            uid = form.save()
            request.user = User.objects.filter(pk=uid).first()
        # This should never happen
        if not request.user or not request.user.is_active:
            raise ValidationError(
                _(
                    "There was an error when logging in. Please contact the organiser for further help."
                )
            )
        login(
            request, request.user, backend="django.contrib.auth.backends.ModelBackend"
        )

    @property
    def label(self):
        return _("Account")

    @property
    def _title(self):
        return _(
            "That’s it about your proposal! We now just need a way to contact you."
        )

    @property
    def _text(self):
        return _(
            "To create your proposal, you need an account on this page. This not only gives us a way to contact you, it also gives you the possibility to edit your proposal or to view its current state."
        )


class ProfileStep(FormFlowStep):
    identifier = "profile"
    icon = "address-card-o"
    form_class = SpeakerProfileForm
    template_name = "cfp/event/submission_profile.html"
    priority = 75
    field_keys = ["name", "biography", "avatar", "availabilities"]
    always_required_fields = {"name"}
    label_model = SpeakerProfile

    def set_data(self, data):
        super().set_data(data)
        # The ProfilePictureWidget stores the chosen action (upload, select_N,
        # remove, keep) in a hidden input ``avatar_action`` that lives outside
        # cleaned_data.  Persist it so the widget can reconstruct the correct
        # state when the form is later rebuilt from session storage.
        if hasattr(self, "request") and self.request.method == "POST":
            avatar_action = self.request.POST.get("avatar_action")
            if avatar_action and avatar_action != "keep":
                self.cfp_session["data"][self.identifier]["avatar_action"] = (
                    avatar_action
                )

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        user_data = copy.deepcopy(self.cfp_session.get("data", {}).get("user", {}))
        user = None
        if user_data and user_data.get("user_id"):
            user = User.objects.filter(pk=user_data["user_id"]).first()
        if not user and self.request.user.is_authenticated:
            user = self.request.user
        result["user"] = user
        result["name"] = user.name if user else user_data.get("register_name")
        result["read_only"] = False
        result["essential_only"] = True
        return result

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        email = getattr(self.request.user, "email", None)
        if email is None:
            data = self.cfp_session.get("data", {}).get("user", {})
            email = data.get("register_email", "")
        return result

    def done(self, request, draft=False):
        form = self.get_form(from_storage=True)
        form.is_valid()
        form.user = request.user
        form.save()

    @property
    def label(self):
        return _("Profile")

    @property
    def _title(self):
        return _("Tell us something about yourself!")

    @property
    def _text(self):
        return _(
            "This information will be publicly displayed next to your session - you can always edit for as long as proposals are still open."
        )


DEFAULT_STEPS = (InfoStep, QuestionsStep, UserStep, ProfileStep)
