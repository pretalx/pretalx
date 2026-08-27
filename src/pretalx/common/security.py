# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import time

from django.conf import settings
from django.contrib.auth import login as auth_login


class SessionInvalidError(Exception):
    pass


class SessionReauthRequiredError(Exception):
    pass


def assert_session_valid(request):
    request.session.setdefault("pretalx_auth_login_time", int(time.time()))

    if not request.session.get("pretalx_auth_long_session", False):
        last_used = request.session.get("pretalx_auth_last_used", time.time())
        if (
            time.time() - request.session["pretalx_auth_login_time"]
            > settings.PRETALX_SESSION_TIMEOUT_ABSOLUTE
        ):
            request.session["pretalx_auth_login_time"] = 0
            raise SessionInvalidError
        if time.time() - last_used > settings.PRETALX_SESSION_TIMEOUT_RELATIVE:
            raise SessionReauthRequiredError

    request.session["pretalx_auth_last_used"] = int(time.time())
    return True


def session_login(request, user, keep_logged_in=False):
    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    session_reauth(request)
    request.session["pretalx_auth_long_session"] = keep_logged_in


def session_reauth(request):
    timestamp = int(time.time())
    request.session["pretalx_auth_login_time"] = timestamp
    request.session["pretalx_auth_last_used"] = timestamp
