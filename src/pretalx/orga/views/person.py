# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View
from django_context_decorator import context
from django_scopes import scopes_disabled

from pretalx.api.versions import CURRENT_VERSION
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import Button
from pretalx.common.views.generic import get_next_url
from pretalx.common.views.helpers import is_form_bound
from pretalx.orga.views.event import EventPermissionRequired
from pretalx.person.forms import AuthTokenForm, LoginInfoForm, OrgaProfileForm


class UserSettings(TemplateView):
    form_class = LoginInfoForm
    template_name = "orga/user.html"

    def get_success_url(self) -> str:
        return reverse("orga:user.view")

    @context
    @cached_property
    def login_form(self):
        return LoginInfoForm(
            user=self.request.user,
            data=self.request.POST if is_form_bound(self.request, "login") else None,
        )

    @context
    def current_version(self):
        return CURRENT_VERSION

    @context
    @cached_property
    def profile_form(self):
        return OrgaProfileForm(
            instance=self.request.user,
            data=self.request.POST if is_form_bound(self.request, "profile") else None,
        )

    @context
    @cached_property
    def token_form(self):
        return AuthTokenForm(
            user=self.request.user,
            data=self.request.POST if is_form_bound(self.request, "token") else None,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile_submit"] = [Button(name="form", value="profile")]
        context["login_submit"] = [Button(name="form", value="login")]
        context["token_submit"] = [Button(name="form", value="token")]
        return context

    def post(self, request, *args, **kwargs):
        if self.login_form.is_bound and self.login_form.is_valid():
            self.login_form.save()
            messages.success(request, phrases.base.saved)
            request.user.log_action("pretalx.user.password.update")
        elif self.profile_form.is_bound and self.profile_form.is_valid():
            self.profile_form.save()
            messages.success(request, phrases.base.saved)
            request.user.log_action("pretalx.user.profile.update")
        elif self.token_form.is_bound and self.token_form.is_valid():
            token = self.token_form.save()
            if token:
                messages.info(
                    request,
                    _(
                        "This is your new API token. Please make sure to save it, as it will not be shown again:"
                    )
                    + f" {token.token}",
                )
                request.user.log_action(
                    "pretalx.user.token.create", data=token.serialize()
                )
        elif token_id := request.POST.get("tokenupgrade"):
            token = request.user.api_tokens.filter(pk=token_id).first()
            token.version = CURRENT_VERSION
            token.save()
            # TODO: log versions as old/new
            request.user.log_action(
                "pretalx.user.token.upgrade", data=token.serialize()
            )
            messages.success(request, _("The API token has been upgraded."))
        elif token_id := request.POST.get("revoke"):
            with scopes_disabled():
                token = request.user.api_tokens.filter(pk=token_id).first()
                if token:
                    token.expires = now()
                    token.save()
                    request.user.log_action(
                        "pretalx.user.token.revoke", data=token.serialize()
                    )
                    messages.success(request, _("The API token was revoked."))
        else:
            messages.error(self.request, phrases.base.error_saving_changes)
            return self.get(request, *args, **kwargs)
        return redirect(self.get_success_url())

    @context
    @cached_property
    def tokens(self):
        with scopes_disabled():
            return self.request.user.api_tokens.all().order_by("-expires")


class SubuserView(View):
    def dispatch(self, request, *args, **kwargs):
        request.user.is_administrator = request.user.is_superuser
        request.user.is_superuser = False
        request.user.save(update_fields=["is_administrator", "is_superuser"])
        messages.success(
            request, _("You are now an administrator instead of a superuser.")
        )
        if url := get_next_url(request):
            return redirect(url)
        return redirect(reverse("orga:event.list"))


class PreferencesView(EventPermissionRequired, View):
    permission_required = "event.orga_access_event"

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            table_name = data.get("table_name")
            reset = data.get("reset", False)

            if not table_name:
                return JsonResponse({"error": "table_name is required"}, status=400)

            preferences = request.user.get_event_preferences(request.event)

            if reset:
                preferences.clear(f"tables.{table_name}.columns", commit=True)
            else:
                columns = data.get("columns", [])
                if not isinstance(columns, list):
                    return JsonResponse({"error": "columns must be a list"}, status=400)

                preferences.set(f"tables.{table_name}.columns", columns, commit=True)

            return JsonResponse({"success": True})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
