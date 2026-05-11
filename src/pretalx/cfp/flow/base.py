# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Jahongir
# SPDX-FileContributor: Laura Klünder

import copy
import json
from contextlib import suppress
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import UploadedFile
from django.forms import FileField, ValidationError
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateResponseMixin

from pretalx.cfp.flow.utils import cfp_session, i18n_string, serialize_value
from pretalx.submission.models import SubmissionStates
from pretalx.submission.models.submission import Submission


class BaseCfPStep:
    icon = "pencil"

    def __init__(self, event):
        self.event = event
        self.request = None

    @property
    def identifier(self):
        raise NotImplementedError

    @property
    def label(self):
        raise NotImplementedError

    @property
    def priority(self):
        return 100

    def is_applicable(self, request):
        return True

    def is_completed(self, request):
        raise NotImplementedError

    @cached_property
    def cfp_session(self):
        return cfp_session(self.request)

    def get_next_applicable(self, request):
        next_step = getattr(self, "_next", None)
        if next_step:
            if not next_step.is_applicable(request):
                return next_step.get_next_applicable(request)
            return next_step

    def get_prev_applicable(self, request):
        previous_step = getattr(self, "_previous", None)
        if previous_step:
            if not previous_step.is_applicable(request):
                return previous_step.get_prev_applicable(request)
            return previous_step

    def get_prev_url(self, request):
        prev = self.get_prev_applicable(request)
        if prev:
            return prev.get_step_url(request, query={"draft": False})

    def get_next_url(self, request):
        next_step = self.get_next_applicable(request)
        if next_step:
            return next_step.get_step_url(request)

    def get_step_url(self, request, query=None):
        kwargs = request.resolver_match.kwargs
        kwargs["step"] = self.identifier
        url = reverse("cfp:event.submit", kwargs=kwargs)
        new_query = request.GET.copy()
        query = query or {}
        for key, value in query.items():
            if value is False:
                new_query.pop(key, None)
            else:
                new_query.update({key: value})
        if new_query:
            url += f"?{new_query.urlencode()}"
        return url

    def get(self, request):
        return HttpResponseNotAllowed([])  # pragma: no cover

    def post(self, request):
        return HttpResponseNotAllowed([])  # pragma: no cover

    def done(self, request, draft=False):
        pass

    def get_csp_update(self, request):
        pass


class TemplateFlowStep(TemplateResponseMixin, BaseCfPStep):
    template_name = "cfp/event/submission_base.html"

    def get_context_data(self, **kwargs):
        kwargs.setdefault("step", self)
        kwargs.setdefault("event", self.event)
        kwargs.setdefault("prev_url", self.get_prev_url(self.request))
        kwargs.setdefault("next_url", self.get_next_url(self.request))
        kwargs.setdefault(
            "cfp_flow",
            [
                step
                for step in self.event.cfp_flow.steps
                if step.is_applicable(self.request)
            ],
        )
        return kwargs

    def render(self, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get(self, request):
        self.request = request
        return self.render()

    @property
    def identifier(self):
        raise NotImplementedError


class FormFlowStep(TemplateFlowStep):
    form_class = None
    file_storage = FileSystemStorage(str(Path(settings.MEDIA_ROOT) / "cfp_uploads"))
    always_required_fields = set()
    field_keys = []
    label_model = None

    def get_form_initial(self):
        return copy.deepcopy(
            self.cfp_session.get("initial", {}).get(self.identifier, {})
        )

    def get_form_data(self):
        return copy.deepcopy(self.cfp_session.get("data", {}).get(self.identifier, {}))

    def get_form(self, from_storage=False):
        stored_files = self.get_files()
        if self.request.method == "GET" or from_storage:
            data = self.get_form_data()
            form = self.form_class(
                data=data or None,
                initial=self.get_form_initial() if not data else {},
                files=stored_files,
                **self.get_form_kwargs(),
            )
        else:
            # Merge stored session files so previously uploaded files
            # survive back-navigation without requiring re-upload.
            files = self.request.FILES.copy()
            for key, value in (stored_files or {}).items():
                if key not in files:
                    files[key] = value
            form = self.form_class(
                data=self.request.POST, files=files, **self.get_form_kwargs()
            )
        self._annotate_stored_filenames(form, stored_files)
        return form

    def _annotate_stored_filenames(self, form, stored_files):
        if not stored_files:
            return
        for field_name, field_obj in form.fields.items():
            if isinstance(field_obj, FileField) and field_name in stored_files:
                stored_name = stored_files[field_name].name
                note = (
                    '<span class="stored-file-indicator">'
                    '<i class="fa fa-file"></i> '
                    f"{stored_name}</span><br>"
                )
                existing = field_obj.help_text or ""
                field_obj.help_text = f"{note} {existing}".strip()

    def is_completed(self, request):
        self.request = request
        return self.get_form(from_storage=True).is_valid()

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["form"] = self.get_form()
        result["text"] = self.text
        result["title"] = self.title
        previous_data = self.cfp_session.get("data")
        result["submission_title"] = previous_data.get("info", {}).get("title")
        return result

    def is_valid(self):
        form = self.get_form()
        if not form.is_valid():
            error_message = "\n\n".join(
                (f"{form.fields[key].label}: " if key != "__all__" else "")
                + " ".join(values)
                for key, values in form.errors.items()
            )
            messages.error(self.request, error_message)
            return False
        self.set_data(form.cleaned_data)
        own_files = {k: v for k, v in form.files.items() if k in form.fields}
        try:
            self.set_files(own_files)
        except ValidationError as e:
            messages.error(self.request, e.message)
            return False
        return True

    def post(self, request):
        self.request = request
        if not self.is_valid():
            return self.get(request)
        next_url = self.get_next_url(request)
        if next_url:
            return redirect(next_url)
        return self.get(request)

    def set_data(self, data):
        serialize_data = {}
        for key, value in data.items():
            with suppress(FileNotFoundError):
                if not getattr(value, "file", None):
                    serialize_data[key] = value
        self.cfp_session["data"][self.identifier] = json.loads(
            json.dumps(serialize_data, default=serialize_value)
        )

    def get_files(self):
        saved_files = self.cfp_session["files"].get(self.identifier, {})
        files = {}
        dropped = []
        for field, field_dict in saved_files.items():
            file_data = field_dict.copy()
            tmp_name = file_data.pop("tmp_name")
            try:
                files[field] = UploadedFile(
                    file=self.file_storage.open(tmp_name), **file_data
                )
            except FileNotFoundError:
                # The CfP temp upload has been cleaned up (e.g. by the OS
                # temp-reaper between sessions); drop the broken entry so
                # the user can re-upload instead of seeing a 500.
                dropped.append(field)
        if dropped:
            remaining = {k: v for k, v in saved_files.items() if k not in dropped}
            self.cfp_session["files"][self.identifier] = remaining
        return files or None

    def set_files(self, files):
        """Persist uploaded files into the CfP session storage.

        Raises ``ValidationError`` if the underlying OS temp file has
        been removed between request parsing and storage, so the caller
        can surface a re-upload prompt instead of propagating a
        ``FileNotFoundError`` up to a 500 response."""
        for field, field_file in files.items():
            try:
                tmp_filename = self.file_storage.save(field_file.name, field_file)
            except FileNotFoundError as e:
                raise ValidationError(
                    _("Your file upload could not be processed. Please try again.")
                ) from e
            file_dict = {
                "tmp_name": tmp_filename,
                "name": field_file.name,
                "content_type": field_file.content_type,
                "size": field_file.size,
                "charset": field_file.charset,
            }
            data = self.cfp_session["files"].get(self.identifier, {})
            data[field] = file_dict
            self.cfp_session["files"][self.identifier] = data

    @cached_property
    def config(self):
        return self.event.cfp_flow.config.get("steps", {}).get(self.identifier, {})

    @property
    def title(self):
        return i18n_string(self.config.get("title", self._title), self.event.locales)

    @property
    def text(self):
        return i18n_string(self.config.get("text", self._text), self.event.locales)

    def get_extra_form_kwargs(self):
        # Used for form kwargs that do not depend on the request/event, but should
        # always be used, particularly in the CfP editor
        return {}

    def get_form_kwargs(self):
        return {
            "event": self.request.event,
            "field_configuration": self.config.get("fields"),
            **self.get_extra_form_kwargs(),
        }


class DedraftMixin:
    dedraft_key = "instance"

    @cached_property
    def dedraft_submission(self):
        with suppress(Submission.DoesNotExist, KeyError):
            code = self.cfp_session.get("code")
            if self.request.user.is_authenticated and code:
                return Submission.all_objects.get(
                    event=self.event,
                    code=code,
                    state=SubmissionStates.DRAFT,
                    speakers__user=self.request.user,
                )

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        if self.dedraft_submission:
            result[self.dedraft_key] = self.dedraft_submission
        return result
