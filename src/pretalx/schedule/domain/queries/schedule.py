# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.schedule.models import TalkSlot


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


def get_schedule(event, version, *, queryset=None):
    """Look up a schedule by version, or return None.

    Pass a version or the special strings ``"wip"`` or ``"latest"``.
    """
    queryset = event.schedules.all() if queryset is None else queryset
    queryset = queryset.select_related("event")
    if version == "wip":
        return queryset.filter(version__isnull=True).first()
    if version == "latest":
        if not event.current_schedule:
            return None
        return queryset.filter(pk=event.current_schedule.pk).first()
    return queryset.filter(version=version).first()


def public_talk_slots(event):
    """Talk slots visible to non-orga viewers of ``event``."""
    return TalkSlot.objects.filter(schedule__event=event, is_visible=True).exclude(
        schedule__version__isnull=True
    )
