# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction


def delete_room(room, *, log_kwargs=None):
    """Delete ``room`` together with the activity log entries pointing at it.

    Raises ``django.db.models.deletion.ProtectedError`` if the room is still
    referenced by a ``TalkSlot``; callers translate that into a user-facing
    error.
    """
    with transaction.atomic():
        room.logged_actions().delete()
        room.delete(log_kwargs=log_kwargs or {})
