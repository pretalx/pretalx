# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.models import ActivityLog


def actions_by(person):
    """All :class:`ActivityLog` rows whose actor is ``person``.

    Companion to ``LogMixin.logged_actions`` (which returns rows where the
    object is ``person``)."""
    return ActivityLog.objects.filter(person=person).select_related("event")
