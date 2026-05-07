# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import get_language

from pretalx.person.models import User


def create_user(*, email, name="", password=None, event=None, **kwargs):
    """Single entry point for creating ``User`` rows.

    When ``password`` is ``None``, a random password and a fresh
    ``pw_reset_token`` are generated so the new user can pick a real
    password via the standard recovery URL — this is the invitation
    flow used for speakers that are created rather than invited.

    Passing ``event`` materialises a ``SpeakerProfile`` for that event.

    Extra ``**kwargs`` are forwarded to ``User.objects.create_user`` so
    callers can set ``locale``, ``timezone`` etc.; we default the latter
    two to the active request language/timezone rather than letting the
    model fall back to ``settings.LANGUAGE_CODE`` / ``UTC``.
    """
    kwargs["email"] = email.lower().strip()
    kwargs["name"] = (name or "").strip()
    kwargs.setdefault("locale", get_language())
    kwargs.setdefault("timezone", timezone.get_current_timezone_name())
    if password is None:
        kwargs["password"] = get_random_string(32)
        kwargs["pw_reset_token"] = get_random_string(32)
        kwargs["pw_reset_time"] = timezone.now() + dt.timedelta(days=60)
    else:
        kwargs["password"] = password

    user = User.objects.create_user(**kwargs)
    if event:
        user.get_speaker(event=event)
    return user
