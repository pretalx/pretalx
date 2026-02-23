# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import urllib
from collections import defaultdict
from contextlib import suppress
from urllib.parse import quote

from csp.decorators import csp_exempt
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils.functional import cached_property
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_context_decorator import context
from formtools.wizard.forms import ManagementForm
from rules.contrib.views import PermissionRequiredMixin

from pretalx.common.forms import SearchForm
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.models.file import CachedFile
from pretalx.common.text.path import safe_filename
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import Button, back_button

SessionStore = import_string(f"{settings.SESSION_ENGINE}.SessionStore")


class Filterable:
    filter_fields = []
    default_filters = []

    def get_default_filters(self):
        return self.default_filters

    def filter_queryset(self, qs):
        if self.filter_fields:
            qs = self._handle_filter(qs)
        if "q" in self.request.GET:
            query = urllib.parse.unquote(self.request.GET["q"])
            qs = self.handle_search(qs, query, self.get_default_filters())
        if (
            (filter_form := self.filter_form)
            and filter_form.is_valid()
            and hasattr(filter_form, "filter_queryset")
        ):
            qs = filter_form.filter_queryset(qs)
        return qs

    def _handle_filter(self, qs):
        for key in self.request.GET:  # Do NOT use items() to preserve multivalue fields
            # There is a special case here: we hack in OR lookups by allowing __ in values.
            lookups = defaultdict(list)
            values = self.request.GET.getlist(key)
            for value in values:
                value_parts = value.split("__", maxsplit=1)
                if len(value_parts) > 1 and value_parts[0] in self.filter_fields:
                    _key = value_parts[0]
                    _value = value_parts[1]
                else:
                    _key = key
                    _value = value_parts[0]
                if _key in self.filter_fields and _value:
                    if "__isnull" in _key:
                        # We don't append to the list here, because that's not meaningful
                        # in a boolean lookup
                        lookups[_key] = _value == "on"
                    else:
                        _key = f"{_key}__in"
                        lookups[_key].append(_value)
            _filters = Q()
            for _key, value in lookups.items():
                _filters |= Q(**{_key: value})
            qs = qs.filter(_filters)
        return qs

    @staticmethod
    def handle_search(qs, query, filters):
        _filters = [Q(**{field: query}) for field in filters]
        if len(_filters) > 1:
            _filter = _filters[0]
            for additional_filter in _filters[1:]:
                _filter = _filter | additional_filter
            qs = qs.filter(_filter)
        elif _filters:
            qs = qs.filter(_filters[0])
        return qs

    @context
    @cached_property
    def search_form(self):
        return SearchForm(self.request.GET if "q" in self.request.GET else None)

    @context
    @cached_property
    def filter_form(self):
        if hasattr(self, "filter_form_class"):
            return self.filter_form_class(self.request.GET, event=self.request.event)
        if hasattr(self, "get_filter_form"):
            return self.get_filter_form()
        if self.filter_fields:
            _form = forms.modelform_factory(self.model, fields=self.filter_fields)(
                self.request.GET
            )
            for field in _form.fields.values():
                field.required = False
                if hasattr(field, "queryset"):
                    field.queryset = field.queryset.filter(event=self.request.event)
            return _form
        return None


class PermissionRequired(PermissionRequiredMixin):
    write_permission_required = None
    create_permission_required = None
    read_only_form_class = False

    @cached_property
    def object(self):
        return self.get_object()

    @cached_property
    def permission_object(self):
        if hasattr(self, "get_permission_object"):
            return self.get_permission_object()
        return self.object

    @context
    @cached_property
    def permission_action(self):
        kwargs = getattr(self, "kwargs", None)
        if kwargs and not any(_id in self.kwargs for _id in ("pk", "code")):
            if permission := self.create_permission_required:
                # If there is a create_permission and we don't have it, raise
                if not self._check_permission(permission):
                    raise Http404
                return "create"
            if self._check_permission(self.write_permission_required):
                # If there is no create permission, we're probably not in an object view
                return "create"
            return "view"
        if self._check_permission(self.write_permission_required):
            return "edit"
        return "view"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cls = self.get_form_class()
        if self.read_only_form_class or issubclass(cls, ReadOnlyFlag):
            kwargs["read_only"] = self.permission_action == "view"
        event = getattr(self.request, "event", None)
        if event and issubclass(self.form_class, PretalxI18nModelForm):
            kwargs["locales"] = event.locales
        return kwargs

    def _check_permission(self, permission_name):
        return self.request.user.has_perm(permission_name, self.permission_object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "get_permission_object"):
            for key in ("permission_object", "object"):
                if getattr(self, key, None):
                    self.get_permission_object = lambda self, key=key: getattr(
                        self, key
                    )  # noqa: E731

    def has_permission(self):
        result = None
        with suppress(Exception):
            result = super().has_permission()
        if not result:
            request = getattr(self, "request", None)
            if request and hasattr(request, "event"):
                key = f"pretalx_event_access_{request.event.pk}"
                if key in request.session:
                    sparent = SessionStore(request.session.get(key))
                    parentdata = []
                    with suppress(Exception):
                        parentdata = sparent.load()
                    return "event_access" in parentdata
        return result

    def get_login_url(self):
        """We do this to avoid leaking data about existing pages."""
        raise Http404

    def handle_no_permission(self):
        request = getattr(self, "request", None)
        if (
            request
            and hasattr(request, "event")
            and request.user.is_anonymous
            and "cfp" in request.resolver_match.namespaces
        ):
            params = "&" + request.GET.urlencode() if request.GET else ""
            return redirect(
                request.event.urls.login + f"?next={quote(request.path)}" + params
            )
        raise Http404


class EventPermissionRequired(PermissionRequired):
    def get_permission_object(self):
        return self.request.event


class SensibleBackWizardMixin:
    def post(self, *args, **kwargs):
        """Don't redirect if user presses the prev.

        step button, save data instead. The rest of this is copied from
        WizardView. We want to save data when hitting "back"!
        """
        wizard_goto_step = self.request.POST.get("wizard_goto_step")
        management_form = ManagementForm(self.request.POST, prefix=self.prefix)
        if not management_form.is_valid():
            raise forms.ValidationError(
                _("ManagementForm data is missing or has been tampered with."),
                code="missing_management_form",
            )

        form_current_step = management_form.cleaned_data["current_step"]
        if (
            form_current_step != self.steps.current
            and self.storage.current_step is not None
        ):
            # form refreshed, change current step
            self.storage.current_step = form_current_step

        # get the form for the current step
        form = self.get_form(data=self.request.POST, files=self.request.FILES)

        # and try to validate
        if form.is_valid():
            # if the form is valid, store the cleaned data and files.
            self.storage.set_step_data(self.steps.current, self.process_step(form))
            self.storage.set_step_files(
                self.steps.current, self.process_step_files(form)
            )

            # check if the current step is the last step
            if wizard_goto_step and wizard_goto_step in self.get_form_list():
                return self.render_goto_step(wizard_goto_step)
            if self.steps.current == self.steps.last:
                # no more steps, render done view
                return self.render_done(form, **kwargs)
            # proceed to the next step
            return self.render_next_step(form)
        return self.render(form)


class SocialMediaCardMixin:
    def get_image(self):
        raise NotImplementedError

    @csp_exempt()
    def get(self, request, *args, **kwargs):
        with suppress(Exception):
            image = self.get_image()
            if image:
                return FileResponse(image)
        if self.request.event.og_image:
            return FileResponse(self.request.event.og_image)
        if self.request.event.logo:
            return FileResponse(self.request.event.logo)
        if self.request.event.header_image:
            return FileResponse(self.request.event.header_image)
        raise Http404


class PaginationMixin:
    DEFAULT_PAGINATION = 50

    def get_paginate_by(self, queryset=None):
        skey = "stored_page_size_" + self.request.resolver_match.url_name
        default = (
            self.request.session.get(skey)
            or getattr(self, "paginate_by", None)
            or self.DEFAULT_PAGINATION
        )
        if self.request.GET.get("page_size"):
            try:
                if max_page_size := getattr(
                    self, "max_page_size", settings.MAX_PAGINATION_LIMIT
                ):
                    size = min(max_page_size, int(self.request.GET.get("page_size")))
                else:
                    size = int(self.request.GET.get("page_size"))
                self.request.session[skey] = size
                return size
            except ValueError:
                return default
        return default

    def get_context_data(self, **kwargs):
        from pretalx.common.views.generic import CRUDView  # noqa: PLC0415

        ctx = super().get_context_data(**kwargs)
        if isinstance(self, CRUDView) and self.permission_action != "list":
            return ctx
        return ctx


class ActionConfirmMixin:
    """
    Mixin providing all variables needed for the action_confirm.html template,
    which you can either include via common/includes/action_confirm.html, or
    use directly as common/action_confirm.html.

    Implement at least:
    - action_object_name

    Implement probably:
    - action_back_url

    If the view is not a delete view, also implement:
    - action_confirm_label
    - action_confirm_color
    - action_confirm_icon
    - action_title
    - action_text
    """

    template_name = "common/action_confirm.html"
    action_object_name = None  # Shown between the title and the warning text
    action_text = phrases.base.delete_warning  # Use this for context or warnings
    action_title = phrases.base.delete_confirm_heading  # Shown as heading and as title
    action_confirm_color = "danger"
    action_confirm_icon = "trash"
    action_confirm_label = phrases.base.delete_button

    @property
    def action_back_url(self):
        url_param = self.request.GET.get("next") or self.request.GET.get("back")
        if url_param:
            return urllib.parse.unquote(url_param)
        # Fallback if we don't have a next parameter: go up one level
        return self.request.path.rsplit("/", 2)[0]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action_text"] = self.action_text
        ctx["action_title"] = self.action_title
        ctx["action_object_name"] = self.action_object_name
        ctx["submit_buttons_extra"] = [back_button(self.action_back_url or "..")]
        ctx["submit_buttons"] = [
            Button(
                color=self.action_confirm_color,
                icon=self.action_confirm_icon,
                label=self.action_confirm_label,
            )
        ]
        return ctx


def reorder_queryset(queryset, id_list):
    """Update position fields on a queryset given an ordered list of PKs.

    Validates that each PK exists in the queryset (404 otherwise).
    """
    objects = {str(obj.pk): obj for obj in queryset}
    to_update = []
    for index, pk in enumerate(id_list):
        if pk not in objects:
            raise Http404
        obj = objects[pk]
        obj.position = index
        to_update.append(obj)
    queryset.model.objects.bulk_update(to_update, ["position"])


class OrderActionMixin:
    """Change an ordered model with a POST endpoint to a CRUDView list view."""

    extra_actions = {
        "list": {"post": "order_handler"},
    }

    def order_handler(self, request, *args, **kwargs):
        order = request.POST.get("order")
        if order:
            reorder_queryset(self.get_queryset(), order.split(","))
        return self.list(request, *args, **kwargs)


class AsyncFileDownloadMixin:
    """Mixin for views that generate and serve files asynchronously via Celery.

    Tasks store results in a CachedFile, tracked by Celery task ID.

    Subclasses must implement:
    - get_error_redirect_url(): URL to redirect to on error
    - get_async_download_filename(): Filename for the download
    - start_async_task(cached_file): Start the Celery task, return AsyncResult

    Optional overrides:
    - async_download_expiry: timedelta for CachedFile expiry (default: 24 hours)
    - async_download_content_type: Content-Type for CachedFile (default: "application/zip")
    - get_async_download_context(): Extra context for templates
    - get_async_waiting_template(): Template for waiting page
    """

    async_download_expiry = dt.timedelta(hours=24)
    async_download_content_type = "application/zip"

    def get_error_redirect_url(self):
        raise NotImplementedError

    def get_async_download_filename(self):
        raise NotImplementedError

    def start_async_task(self, cached_file):
        raise NotImplementedError

    def get_async_download_context(self):
        return {}

    def get_async_waiting_template(self):
        return "orga/includes/async_download_waiting.html"

    def handle_async_download(self, request):
        cached_file_id = request.GET.get("cached_file")
        if cached_file_id:
            try:
                cached_file = CachedFile.objects.filter(id=cached_file_id).first()
            except (ValueError, ValidationError):
                cached_file = None
            if cached_file and cached_file.file:
                return self._serve_cached_file(request, cached_file)
            messages.error(request, _("Export file not found. Please try again."))
            return redirect(self.get_error_redirect_url())
        async_id = request.GET.get("async_id")
        if async_id:
            return self._check_task_status(request, async_id)
        return self._start_task(request)

    def _start_task(self, request):
        cached_file = CachedFile.objects.create(
            expires=now() + self.async_download_expiry,
            filename=self.get_async_download_filename(),
            content_type=self.async_download_content_type,
        )
        result = self.start_async_task(cached_file)

        if settings.CELERY_TASK_ALWAYS_EAGER:
            cached_file.refresh_from_db()
            return self._serve_cached_file(request, cached_file)

        return redirect(f"{request.path}?async_id={result.id}")

    def _check_task_status(self, request, async_id):
        from celery.result import AsyncResult  # noqa: PLC0415

        result = AsyncResult(async_id)
        is_ready = result.ready()
        is_successful = result.successful() if is_ready else False

        cached_file = None
        if is_ready and is_successful and result.result:
            try:
                cached_file = CachedFile.objects.filter(id=result.result).first()
            except (ValueError, ValidationError):
                cached_file = None
            is_successful = cached_file is not None and bool(cached_file.file)

        context = {"async_id": async_id, **self.get_async_download_context()}

        if request.headers.get("HX-Request"):
            if is_ready:
                if is_successful:
                    context["download_url"] = (
                        f"{request.path}?cached_file={result.result}"
                    )
                    return render(
                        request, "orga/includes/async_download.html#success", context
                    )
                context["back_url"] = self.get_error_redirect_url()
                return render(
                    request, "orga/includes/async_download.html#error", context
                )
            return render(
                request, "orga/includes/async_download.html#waiting-spinner", context
            )

        if is_ready:
            if is_successful:
                return self._serve_cached_file(request, cached_file)
            messages.error(request, _("Export failed. Please try again."))
            return redirect(self.get_error_redirect_url())

        return render(request, self.get_async_waiting_template(), context)

    def _serve_cached_file(self, request, cached_file):
        try:
            response = FileResponse(
                cached_file.file.open("rb"),
                as_attachment=True,
                filename=safe_filename(cached_file.filename),
            )
        except (FileNotFoundError, ValueError):
            messages.error(request, _("Export file not found. Please try again."))
            return redirect(self.get_error_redirect_url())
        return response
