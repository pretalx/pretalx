# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django.http import HttpResponse
from django.urls import path


def dummy_view(request, **kwargs):
    return HttpResponse("ok")


urlpatterns = [path("<slug:event>/test-plugin/", dummy_view, name="test-view")]
