# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.http import HttpResponse
from django.urls import re_path
from django.views import View

from pretalx.common.views.mixins import PermissionRequired
from pretalx.event.models.event import SLUG_REGEX


class DummyPluginView(PermissionRequired, View):
    permission_required = "event.update_event"

    def get_object(self):
        return self.request.event

    def get(self, request, *args, **kwargs):
        return HttpResponse("OK")


urlpatterns = [
    re_path(
        rf"^orga/event/(?P<event>{SLUG_REGEX})/settings/p/tests/$",
        DummyPluginView.as_view(),
        name="settings",
    )
]
