# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from collections import defaultdict

from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases
from pretalx.schedule.models import TalkSlot
from pretalx.submission.domain.queries.submission import (
    annotate_confirmed_signup_count,
    annotate_slot_confirmed_signup_count,
    annotate_slot_requires_signup,
)
from pretalx.submission.enums import SubmissionStates
from pretalx.submission.models import Submission


def get_talk_warnings(
    schedule,
    talk,
    with_speakers=True,
    room_avails=None,
    room_overlap_ids=None,
    speaker_overlaps_by_talk=None,
) -> list:
    """A list of warnings that apply to this slot.

    Warnings are dictionaries with a ``type`` (``room`` or
    ``speaker``, for now) and a ``message`` fit for public display.
    This only considers availability based warnings.

    ``room_overlap_ids`` and ``speaker_overlaps_by_talk`` short-circuit
    the per-talk overlap queries when warnings are fetched in bulk.
    """
    if not talk.start or not talk.submission or not talk.room:
        return []
    warnings = []
    warnings.extend(_signup_capacity_warnings(talk))
    availability = talk.as_availability
    url = talk.submission.orga_urls.base
    if schedule.use_room_availabilities:
        if room_avails is None:
            room_avails = talk.room.full_availability
        if room_avails and not any(
            room_availability.contains(availability)
            for room_availability in room_avails
        ):
            warnings.append(
                {
                    "type": "room",
                    "message": str(
                        _("Room {room_name} is not available at the scheduled time.")
                    ).format(
                        room_name=f"{phrases.base.quotation_open}{talk.room.name}{phrases.base.quotation_close}"
                    ),
                    "url": url,
                }
            )
    if room_overlap_ids is not None:
        overlaps = talk.pk in room_overlap_ids
    else:
        overlaps = (
            TalkSlot.objects.filter(
                schedule=schedule,
                room=talk.room,
                start__lt=talk.real_end,
                end__gt=talk.start,
            )
            .exclude(pk=talk.pk)
            .exists()
        )
    if overlaps:
        warnings.append(
            {
                "type": "room_overlap",
                "message": _(
                    "Another session in the same room overlaps with this one."
                ),
                "url": url,
            }
        )

    for speaker in talk.submission.sorted_speakers:
        if with_speakers:
            speaker_avails = speaker.full_availability
            if speaker_avails and not any(
                speaker_availability.contains(availability)
                for speaker_availability in speaker_avails
            ):
                warnings.append(
                    {
                        "type": "speaker",
                        "speaker": {
                            "name": speaker.get_display_name(),
                            "code": speaker.code,
                        },
                        "message": str(
                            _("{speaker} is not available at the scheduled time.")
                        ).format(speaker=speaker.get_display_name()),
                        "url": url,
                    }
                )
        if speaker_overlaps_by_talk is not None:
            overlaps = speaker.pk in speaker_overlaps_by_talk.get(talk.pk, ())
        else:
            overlaps = (
                TalkSlot.objects.filter(
                    schedule=schedule,
                    submission__speakers=speaker,
                    start__lt=talk.real_end,
                    end__gt=talk.start,
                )
                .exclude(pk=talk.pk)
                .exists()
            )
        if overlaps:
            warnings.append(
                {
                    "type": "speaker",
                    "speaker": {
                        "name": speaker.get_display_name(),
                        "code": speaker.code,
                    },
                    "message": str(
                        _(
                            "{speaker} is scheduled for another session at the same time."
                        )
                    ).format(speaker=speaker.get_display_name()),
                    "url": url,
                }
            )

    return warnings


def _signup_capacity_warnings(talk):
    if (
        not talk.schedule.event.get_feature_flag("attendee_signup")
        or not talk.room
        or not talk.room.capacity
    ):
        return []
    annotated = getattr(talk, "_annotated_requires_signup", None)
    if annotated is None:
        annotated = talk.submission.requires_signup
    if not annotated:
        return []
    capacity = talk.submission.attendee_signup_capacity
    if capacity is None or talk.room.capacity >= capacity:
        return []
    return [
        {
            "type": "signup_room_too_small",
            "message": str(
                _(
                    "Room {room_name} has less space ({room_cap}) "
                    "than the session’s signup capacity ({session_cap})."
                )
            ).format(
                room_name=f"{phrases.base.quotation_open}{talk.room.name}{phrases.base.quotation_close}",
                room_cap=talk.room.capacity,
                session_cap=capacity,
            ),
            "url": talk.submission.orga_urls.base,
        }
    ]


def get_all_talk_warnings(schedule, ids=None, filter_updated=None):
    show_signup_warnings = schedule.event.get_feature_flag("attendee_signup")
    talks = (
        schedule.talks.filter(
            submission__isnull=False, start__isnull=False, room__isnull=False
        )
        .select_related(
            "submission",
            "submission__submission_type",
            "submission__track",
            "room",
            "submission__event",
            "schedule__event",
        )
        .with_sorted_speakers()
        .prefetch_related("submission__speakers__availabilities")
    )
    if show_signup_warnings:
        talks = annotate_slot_requires_signup(talks)
    if filter_updated:
        talks = talks.filter(updated__gte=filter_updated)
    with_speakers = schedule.event.cfp.request_availabilities
    room_avails = defaultdict(
        list,
        {
            room.pk: room.full_availability
            for room in schedule.event.rooms.prefetch_related("availabilities")
        },
    )
    talk_list = list(talks)
    if talk_list:
        is_full_scan = not filter_updated
        subset_pks = None if is_full_scan else {t.pk for t in talk_list}
        # Pull extra slots so overlaps against them are detected: breaks
        # (no submission, excluded from ``talks``) for the full scan, every
        # other scheduled slot for subset mode.
        extra_slots_qs = (
            schedule.talks.filter(start__isnull=False, room__isnull=False)
            .select_related("submission", "submission__submission_type")
            .with_sorted_speakers()
        )
        if is_full_scan:
            extra_slots_qs = extra_slots_qs.filter(submission__isnull=True)
        else:
            extra_slots_qs = extra_slots_qs.exclude(pk__in=subset_pks)
        scan_set = talk_list + list(extra_slots_qs)
        room_overlap_ids, speaker_overlaps_by_talk = _compute_overlap_maps(
            scan_set, subset_pks=subset_pks
        )
    else:
        room_overlap_ids, speaker_overlaps_by_talk = set(), {}
    result = {}
    for talk in talk_list:
        talk_warnings = get_talk_warnings(
            schedule,
            talk=talk,
            with_speakers=with_speakers,
            room_avails=room_avails.get(talk.room_id) if talk.room_id else None,
            room_overlap_ids=room_overlap_ids,
            speaker_overlaps_by_talk=speaker_overlaps_by_talk,
        )
        if talk_warnings:
            result[talk] = talk_warnings
    return result


def _overlapping_pks(entries, subset_pks):
    """Yield pks from ``entries`` that overlap another entry.

    With ``subset_pks=None``, yields both pks of every overlapping pair
    (full pairwise scan). With a ``subset_pks`` set, yields only those pks
    in the subset that overlap anything — each yielded at most once.
    """
    if subset_pks is None:
        for i, (pk_a, start_a, end_a) in enumerate(entries):
            for pk_b, start_b, end_b in entries[i + 1 :]:
                if start_a < end_b and start_b < end_a:
                    yield pk_a
                    yield pk_b
        return
    for pk_a, start_a, end_a in entries:
        if pk_a not in subset_pks:
            continue
        for pk_b, start_b, end_b in entries:
            if pk_b == pk_a:
                continue
            if start_a < end_b and start_b < end_a:
                yield pk_a
                break


def _slot_end(talk):
    if talk.end is not None:
        return talk.end
    if talk.submission_id is None:
        return None
    submission = talk.submission
    duration = submission.duration or submission.submission_type.default_duration
    return talk.start + dt.timedelta(minutes=duration)


def _compute_overlap_maps(talks, subset_pks=None):
    """Room- and speaker-overlap sets over ``talks``.

    If ``subset_pks`` is given, overlap detection still runs against every
    element of ``talks``, but only subset pks appear in the result. Every
    element must have ``with_sorted_speakers()`` applied; otherwise the
    speaker loop below regresses to N+1. Submission-bearing slots without
    an ``end`` fall back to the submission duration, so
    ``submission__submission_type`` must be select_related to avoid N+1.
    """
    by_room = defaultdict(list)
    by_speaker = defaultdict(list)
    for talk in talks:
        end = _slot_end(talk)
        if end is None or end <= talk.start:
            continue
        entry = (talk.pk, talk.start, end)
        by_room[talk.room_id].append(entry)
        if talk.submission_id:
            for speaker in talk.submission.sorted_speakers:
                by_speaker[speaker.pk].append(entry)

    room_overlap_ids = set()
    for entries in by_room.values():
        room_overlap_ids.update(_overlapping_pks(entries, subset_pks))

    speaker_overlaps_by_talk = defaultdict(set)
    for speaker_pk, entries in by_speaker.items():
        for pk in _overlapping_pks(entries, subset_pks):
            speaker_overlaps_by_talk[pk].add(speaker_pk)

    return room_overlap_ids, speaker_overlaps_by_talk


def compute_warnings(schedule) -> dict:
    """A dictionary of warnings to be acknowledged before a release.

    ``talk_warnings`` contains a list of talk-related warnings.
    ``unscheduled`` is the list of talks without a scheduled slot,
    ``unconfirmed`` is the list of submissions that will not be
    visible due to their unconfirmed status, and ``no_track`` are
    submissions without a track in a conference that uses tracks.
    """
    talks = schedule.talks.filter(submission__isnull=False)
    talk_warnings = [
        {"talk": key, "warnings": value}
        for key, value in get_all_talk_warnings(schedule).items()
    ]
    warnings = {
        "talk_warnings": talk_warnings,
        "talk_warnings_count": sum(len(entry["warnings"]) for entry in talk_warnings),
        "unscheduled": talks.filter(start__isnull=True).count(),
        "unconfirmed": talks.exclude(
            submission__state=SubmissionStates.CONFIRMED
        ).count(),
        "no_track": [],
        "signup_room_too_large": [],
        "signup_no_capacity": [],
        "signup_overfull": [],
        "signup_dropped_with_attendees": [],
    }
    if schedule.event.has_active_tracks:
        warnings["no_track"] = talks.filter(submission__track_id__isnull=True)
    if schedule.event.get_feature_flag("attendee_signup"):
        warnings.update(compute_signup_warnings(schedule))
    return warnings


def overbooked_slots_for_room(room):
    slots = room.event.wip_schedule.talks
    if room.capacity is None:
        return slots.none()
    return annotate_slot_confirmed_signup_count(
        slots.filter(submission__isnull=False, room=room, start__isnull=False)
    ).filter(_annotated_confirmed_signup_count__gt=room.capacity)


def compute_signup_warnings(schedule) -> dict:
    result = {
        "signup_room_too_large": [],
        "signup_no_capacity": [],
        "signup_overfull": [],
        "signup_dropped_with_attendees": [],
    }
    no_capacity_slots = schedule.talks.filter(
        submission__isnull=False,
        submission__attendee_signup_capacity__isnull=True,
        room__isnull=False,
        room__capacity__isnull=True,
        start__isnull=False,
    ).select_related(
        "submission",
        "submission__event",
        "submission__submission_type",
        "submission__track",
        "room",
    )
    no_capacity_slots = annotate_slot_requires_signup(no_capacity_slots).filter(
        _annotated_requires_signup=True
    )
    for slot in no_capacity_slots:
        result["signup_no_capacity"].append(
            {"submission": slot.submission, "slot": slot}
        )
    scheduled_slots = schedule.talks.filter(
        submission__isnull=False,
        room__isnull=False,
        start__isnull=False,
        room__capacity__isnull=False,
    ).select_related(
        "submission",
        "submission__event",
        "submission__submission_type",
        "submission__track",
        "room",
    )
    scheduled_slots = annotate_slot_confirmed_signup_count(
        annotate_slot_requires_signup(scheduled_slots)
    ).filter(_annotated_requires_signup=True)
    for slot in scheduled_slots:
        submission = slot.submission
        room_capacity = slot.room.capacity
        explicit_capacity = submission.attendee_signup_capacity
        current_capacity = (
            explicit_capacity if explicit_capacity is not None else room_capacity
        )
        signup_count = getattr(slot, "_annotated_confirmed_signup_count", 0)
        if room_capacity > current_capacity:
            result["signup_room_too_large"].append(
                {
                    "submission": submission,
                    "slot": slot,
                    "room_capacity": room_capacity,
                    "current_capacity": current_capacity,
                }
            )
        # The opposite case (room < capacity) is handled per-talk by
        # ``_signup_capacity_warnings`` so it appears in the editor.
        if signup_count > room_capacity:
            result["signup_overfull"].append(
                {
                    "submission": submission,
                    "slot": slot,
                    "room_capacity": room_capacity,
                    "signup_count": signup_count,
                }
            )
    previous = schedule.previous_schedule
    if previous:
        previous_submission_ids = set(
            previous.scheduled_talks.values_list("submission_id", flat=True)
        )
        current_submission_ids = set(
            schedule.talks.filter(
                submission__isnull=False,
                submission__state=SubmissionStates.CONFIRMED,
                room__isnull=False,
                start__isnull=False,
            ).values_list("submission_id", flat=True)
        )
        dropped_ids = previous_submission_ids - current_submission_ids
        if dropped_ids:
            dropped = annotate_confirmed_signup_count(
                Submission.objects.filter(pk__in=dropped_ids).select_related("event")
            ).filter(_annotated_confirmed_signup_count__gt=0)
            for submission in dropped:
                signup_count = getattr(
                    submission, "_annotated_confirmed_signup_count", 0
                )
                result["signup_dropped_with_attendees"].append(
                    {"submission": submission, "signup_count": signup_count}
                )
    return result
