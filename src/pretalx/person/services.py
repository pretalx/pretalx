# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.utils.crypto import get_random_string
from django.utils.timezone import now


def create_user(email, name=None, pw_reset_days=60, event=None):
    from pretalx.person.models import User  # noqa: PLC0415

    user = User.objects.create_user(
        password=get_random_string(32),
        email=email.lower().strip(),
        name=(name or "").strip(),
        pw_reset_token=get_random_string(32),
        pw_reset_time=now() + dt.timedelta(days=pw_reset_days),
    )
    if event:
        user.get_speaker(event=event)
    return user
