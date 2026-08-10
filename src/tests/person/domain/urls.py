# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

# Test-only URLconf: registers the confirm-link URL names that
# get_verification_url() reverses. The real routes ship with the
# verification views (PX-49 tasks 4.1/4.2); drop this file and the
# pytest.mark.urls markers once they exist.

from django.http import HttpResponse
from django.urls import include, path


def _placeholder(request, **kwargs):
    return HttpResponse()


cfp_patterns = (
    [path("<event>/verify/<token>", _placeholder, name="event.verify")],
    "cfp",
)
orga_patterns = (
    [
        path("orga/verify/<token>", _placeholder, name="auth.verify"),
        path(
            "orga/event/<event>/verify/<token>", _placeholder, name="event.auth.verify"
        ),
    ],
    "orga",
)

urlpatterns = [path("", include(cfp_patterns)), path("", include(orga_patterns))]
