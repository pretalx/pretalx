# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import sys

from django.conf import settings
from django.contrib import messages
from django.core import cache
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView
from django_context_decorator import context
from django_scopes import scopes_disabled

from pretalx.celery_app import app
from pretalx.common.exceptions import UserDeletionError
from pretalx.common.image import gravatar_csp
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.text.phrases import phrases
from pretalx.common.update_check import check_result_table, update_check
from pretalx.common.views.generic import OrgaCRUDView
from pretalx.common.views.mixins import PermissionRequired
from pretalx.orga.forms.admin import UpdateSettingsForm
from pretalx.orga.tables.admin import AdminUserTable
from pretalx.person.models import User


class AdminDashboard(PermissionRequired, TemplateView):
    template_name = "orga/admin/admin.html"
    permission_required = "person.administrator_user"

    @context
    def queue_length(self):
        if settings.CELERY_TASK_ALWAYS_EAGER:
            return None
        try:
            client = app.broker_connection().channel().client
            return client.llen("celery")
        except Exception as e:
            return str(e)

    @context
    def executable(self):
        return sys.executable

    @context
    def pretalx_version(self):
        return settings.PRETALX_VERSION


class UpdateCheckView(PermissionRequired, FormView):
    template_name = "orga/admin/update.html"
    permission_required = "person.administrator_user"
    form_class = UpdateSettingsForm

    def post(self, request, *args, **kwargs):
        if "trigger" in request.POST:
            update_check.apply()
            return redirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, phrases.base.saved)
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, phrases.base.error_saving_changes)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["gs"] = GlobalSettings()
        result["gs"].settings.set("update_check_ack", True)
        return result

    @context
    def result_table(self):
        return check_result_table()

    def get_success_url(self):
        return reverse("orga:admin.update")


class AdminUserView(OrgaCRUDView):
    model = User
    table_class = AdminUserTable
    permission_required = "person.administrator_user"
    paginate_by = 250
    lookup_field = "code"
    path_converter = "slug"
    template_namespace = "orga/admin"
    extra_actions = {"detail": {"get": "detail", "post": "reset_password"}}
    detail_is_update = False

    @gravatar_csp()
    def dispatch(self, *args, **kwargs):
        with scopes_disabled():
            return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        if self.action == "list":
            search = self.request.GET.get("q", "").strip()
            if not search or len(search) < 3:
                return User.objects.none()
            qs = User.objects.filter(
                Q(name__icontains=search) | Q(email__icontains=search)
            )
        else:
            qs = User.objects.all()
        return qs.prefetch_related(
            "teams",
            "teams__organiser",
            "teams__organiser__events",
            "teams__limit_events",
        ).annotate(
            submission_count=Count("submissions", distinct=True),
        )

    def has_permission(self, *args):
        return self.request.user.is_administrator

    def reset_password(self, request, *args, **kwargs):
        user = self.get_object()
        user.reset_password(event=None)
        messages.success(request, phrases.base.password_reset_success)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("orga:admin.user.list")

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        if self.action == "detail":
            result["teams"] = self.object.teams.all().prefetch_related(
                "organiser", "limit_events", "organiser__events"
            )
            result["submissions"] = self.object.submissions.all()
            result["last_actions"] = self.object.own_actions()[:10]
            result["tablist"] = {
                "teams": _("Teams"),
                "submissions": _("Proposals"),
                "actions": _("Last actions"),
            }
        return result

    def get_generic_title(self, instance=None):
        if instance:
            return instance.name
        return _("Users")

    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        try:
            user.shred()
        except UserDeletionError:
            user.deactivate()
        messages.success(request, _("The user has been deleted."))
        return redirect(self.get_success_url())


def healthcheck(request):
    User.objects.exists()

    cache.cache.set("_healthcheck", "1")
    if cache.cache.get("_healthcheck") != "1":
        return HttpResponse("Cache not available.", status=503)

    return HttpResponse()
