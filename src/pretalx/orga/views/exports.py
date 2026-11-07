# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View
from django_context_decorator import context

from pretalx.agenda.tasks import task_export_schedule_html
from pretalx.common.exporter import get_schedule_exporters
from pretalx.common.forms.exports import TableExportForm, TablePickerForm
from pretalx.common.models.exports import TableExport
from pretalx.common.models.file import CachedFile
from pretalx.common.tables.export import (
    get_exportable_table,
    get_exportable_tables,
    get_table_serializer,
)
from pretalx.common.tasks import task_export_table
from pretalx.common.ui import Button, LinkButton
from pretalx.common.views.generic import OrgaCRUDView
from pretalx.common.views.mixins import AsyncFileDownloadMixin, EventPermissionRequired
from pretalx.common.views.redirect import allowed_next_url
from pretalx.orga.tables.table_export import TableExportTable


def can_export(table_class, event, user):
    return table_class is not None and user.has_perm(
        table_class.export_permission, event
    )


def usable_export_tables(event, user):
    return [
        table_class
        for table_class in get_exportable_tables(event).values()
        if can_export(table_class, event, user)
    ]


class TableExportView(OrgaCRUDView):
    model = TableExport
    form_class = TableExportForm
    table_class = TableExportTable
    template_namespace = "orga/exports"
    context_object_name = "table_export"
    create_button_label = _("New export")

    def get_queryset(self):
        event = self.request.event
        usable = {
            table_class.__name__
            for table_class in usable_export_tables(event, self.request.user)
        }
        return event.table_exports.filter(table__in=usable)

    def get_generic_title(self, instance=None):
        if instance:
            return instance.name
        if self.action == "create":
            return _("New export")
        return _("Data exports")

    @cached_property
    def export_table_class(self):
        if self.object:
            return self.object.table_class
        return get_exportable_table(self.request.event, self.request.GET.get("table"))

    @context
    @cached_property
    def export_table_choices(self):
        return [
            (table_class.__name__, table_class.export_name)
            for table_class in usable_export_tables(
                self.request.event, self.request.user
            )
        ]

    @context
    @cached_property
    def table_picker_form(self):
        if self.export_table_class:
            return None
        return TablePickerForm(choices=self.export_table_choices)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["table_class"] = self.export_table_class
        kwargs["require_name"] = True
        kwargs["form_id"] = "table-export-form"
        if self.action == "create" and self.export_table_class:
            kwargs["initial"] = {
                **(kwargs.get("initial") or {}),
                "name": str(self.export_table_class.export_name),
            }
        return kwargs

    def get_form(self, instance, data=None, files=None, **kwargs):
        if not self.export_table_class:
            return None
        if not can_export(
            self.export_table_class, self.request.event, self.request.user
        ):
            raise Http404
        return super().get_form(instance, data=data, files=files, **kwargs)

    def form_handler(self, request, *args, **kwargs):
        if not self.export_table_class:
            return redirect(self.reverse("create"))
        return super().form_handler(request, *args, **kwargs)

    def get_template_names(self):
        if self.action in ("create", "update") and not self.export_table_class:
            return ["orga/exports/tableexport/pick_table.html"]
        return super().get_template_names()

    def get_success_url(self):
        if self.request.POST.get("action") == "download":
            return self.object.urls.run
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        if self.action == "create" and not self.export_table_class:
            result["next_buttons"] = [Button(label=_("Continue"))]
        elif result.get("form"):
            result["submit_buttons"] = [
                Button(
                    name="action",
                    value="download",
                    label=_("Save and download"),
                    icon="download",
                )
            ]
            result["submit_buttons_extra"].append(Button(color="outline-success"))
        return result


class ExportDownloadMixin(AsyncFileDownloadMixin):
    export_config = None

    @cached_property
    def serializer(self):
        return get_table_serializer(
            self.request.event, self.export_config["serializer"]
        )

    def get_export_name(self):
        raise NotImplementedError

    def get_async_download_filename(self):
        name = slugify(self.get_export_name()) or "export"
        timestamp = localtime(timezone=self.request.event.tz).strftime("%Y-%m-%d_%H-%M")
        return (
            f"{self.request.event.slug}_{name}_{timestamp}.{self.serializer.extension}"
        )

    def get_async_download_content_type(self):
        return self.serializer.content_type

    def get_error_redirect_url(self):
        if self.request.user.has_perm("event.update_event", self.request.event):
            return self.request.event.orga_urls.exports
        return self.request.event.orga_urls.base

    def start_async_task(self, cached_file):
        return task_export_table.apply_async(
            kwargs={
                "event_id": self.request.event.pk,
                "user_id": self.request.user.pk,
                "cached_file_id": str(cached_file.id),
                "config": self.export_config,
            }
        )


class AdhocTableExportRun(ExportDownloadMixin, EventPermissionRequired, View):
    permission_required = "event.orga_access_event"

    def get_export_name(self):
        return str(self.table_class.export_name)

    @cached_property
    def table_class(self):
        return get_exportable_table(self.request.event, self.request.POST.get("table"))

    def get_back_url(self):
        return (
            allowed_next_url(self.request.POST.get("next"))
            or self.request.event.orga_urls.base
        )

    def get(self, request, *args, **kwargs):
        if "async_id" in request.GET or "cached_file" in request.GET:
            return self.handle_async_download(request)
        return redirect(self.get_error_redirect_url())

    def post(self, request, *args, **kwargs):
        if not can_export(self.table_class, request.event, request.user):
            raise Http404
        form = TableExportForm(
            data=request.POST,
            event=request.event,
            user=request.user,
            table_class=self.table_class,
            can_save=request.user.has_perm("event.update_event", request.event),
        )
        if not form.is_valid():
            for error in form.errors.values():
                messages.error(request, error[0])
            return redirect(self.get_back_url())
        if form.cleaned_data.get("save"):
            with transaction.atomic():
                table_export = form.save()
                table_export.log_action(".create", person=request.user, orga=True)
            messages.success(request, _("The export has been saved."))
            return redirect(request.event.orga_urls.exports)
        self.export_config = form.save(commit=False).config
        return self.start_async_download(request)


class TableExportRun(ExportDownloadMixin, EventPermissionRequired, View):
    permission_required = "event.update_event"

    @cached_property
    def table_export(self):
        return get_object_or_404(
            self.request.event.table_exports, pk=self.kwargs.get("pk")
        )

    def get_export_name(self):
        return self.table_export.name

    def get(self, request, *args, **kwargs):
        table_class = self.table_export.table_class
        if table_class is None:
            messages.error(
                request, _("This export refers to a table that no longer exists.")
            )
            return redirect(request.event.orga_urls.exports)
        if not can_export(table_class, request.event, request.user):
            raise Http404
        self.export_config = self.table_export.config
        return self.handle_async_download(request)


class MoreExportsView(EventPermissionRequired, TemplateView):
    template_name = "orga/exports/more.html"
    permission_required = "event.update_event"

    @cached_property
    def schedule(self):
        return self.request.event.current_schedule or self.request.event.wip_schedule

    @cached_property
    def exporters(self):
        return get_schedule_exporters(self.request, schedule=self.schedule)

    @context
    @cached_property
    def available_exporters(self):
        return [exporter for exporter in self.exporters if exporter.is_available]

    @context
    @cached_property
    def unavailable_exporters(self):
        return [exporter for exporter in self.exporters if not exporter.is_available]

    @context
    @cached_property
    def zip_buttons(self):
        return [
            Button(label=_("Regenerate Export"), color="secondary"),
            LinkButton(
                href=self.request.event.orga_urls.html_export_download,
                color="primary",
                label=_("Download ZIP"),
            ),
        ]


class HtmlExportTriggerView(EventPermissionRequired, View):
    permission_required = "event.update_event"

    def post(self, request, event):
        cached_file_id = request.event.cache.get("schedule_export_cached_file")
        if cached_file_id:
            CachedFile.objects.filter(id=cached_file_id).delete()
            request.event.cache.delete("schedule_export_cached_file")
        return redirect(request.event.orga_urls.html_export_download)


class HtmlExportDownloadView(AsyncFileDownloadMixin, EventPermissionRequired, View):
    permission_required = "event.update_event"

    def get_error_redirect_url(self):
        return self.request.event.orga_urls.more_exports

    def get_async_download_filename(self):
        return f"{self.request.event.slug}_schedule.zip"

    def start_async_task(self, cached_file):
        result = task_export_schedule_html.apply_async(
            kwargs={
                "event_id": self.request.event.id,
                "cached_file_id": str(cached_file.id),
            }
        )
        self.request.event.cache.set(
            "schedule_export_cached_file", str(cached_file.id), None
        )
        return result

    def get(self, request, event):
        if "async_id" not in request.GET and "cached_file" not in request.GET:
            cached_file_id = request.event.cache.get("schedule_export_cached_file")
            if cached_file_id:
                cached_file = CachedFile.objects.filter(id=cached_file_id).first()
                if cached_file and cached_file.file:
                    return self._serve_cached_file(request, cached_file)
                request.event.cache.delete("schedule_export_cached_file")
        return self.handle_async_download(request)
