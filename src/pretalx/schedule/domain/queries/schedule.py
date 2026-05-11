# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def published_schedules(event):
    """Released schedules of ``event``, most recent first, with the event
    preloaded.

    Callers that render the changelog, the Atom feed, or the static HTML
    export all want the same shape: a flat list of all versioned schedules in
    publication order. Use :func:`pretalx.schedule.domain.changelog.build_changelog`
    when ``previous_schedule`` and ``scheduled_talks`` should also be batched
    in.
    """
    return (
        event.schedules.filter(version__isnull=False)
        .select_related("event")
        .order_by("-published")
    )
