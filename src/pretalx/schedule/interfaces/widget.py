# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.schedule.enums import SlotType
from pretalx.submission.domain.queries.submission import annotate_slot_signup_status


def build_widget_data(
    schedule,
    all_talks=False,
    filter_updated=None,
    all_rooms=False,
    include_blockers=False,
):
    talks = (
        schedule.talks.all() if all_talks else schedule.talks.filter(is_visible=True)
    )
    if not include_blockers:
        talks = talks.exclude(slot_type=SlotType.BLOCKER)
    if filter_updated:
        talks = talks.filter(updated__gte=filter_updated)
    talks = talks.select_related(
        "submission",
        "room",
        "submission__track",
        "submission__event",
        "submission__submission_type",
    ).with_sorted_speakers()
    show_signup = schedule.event.get_feature_flag("attendee_signup")
    if show_signup:
        talks = annotate_slot_signup_status(talks)
    talks = talks.order_by("start")
    all_event_rooms = list(schedule.event.rooms.all())
    rooms = set(all_event_rooms) if all_rooms else set()
    tracks = set()
    speakers = set()
    result = {
        "talks": [],
        "version": schedule.version,
        "schedule_id": schedule.pk,
        "timezone": schedule.event.timezone,
        "event_start": schedule.event.date_from.isoformat(),
        "event_end": schedule.event.date_to.isoformat(),
    }
    show_do_not_record = schedule.event.cfp.request_do_not_record
    for talk in talks:
        if talk.room:
            rooms.add(talk.room)
        if talk.submission:
            if not talk.submission.get_duration() and not (talk.start and talk.end):
                continue
            tracks.add(talk.submission.track)
            speakers |= set(talk.submission.sorted_speakers)
            talk_data = {
                "code": talk.submission.code,
                "id": talk.id,
                "title": talk.submission.title,
                "abstract": talk.submission.abstract,
                "speakers": [
                    speaker.code for speaker in talk.submission.sorted_speakers
                ],
                "track": talk.submission.track_id,
                "start": talk.local_start,
                "end": talk.local_end,
                "room": talk.room_id,
                "duration": talk.submission.get_duration(),
                "updated": talk.updated.isoformat(),
                "content_locale": talk.submission.content_locale,
            }
            if all_talks:
                talk_data["state"] = talk.submission.state
            if show_do_not_record:
                talk_data["do_not_record"] = talk.submission.do_not_record
            if show_signup:
                talk_data["signup_status"] = talk.signup_status
            result["talks"].append(talk_data)
        else:
            result["talks"].append(
                {
                    "id": talk.id,
                    "title": talk.description,
                    "start": talk.start,
                    "end": talk.local_end,
                    "room": talk.room_id,
                    "slot_type": talk.slot_type,
                }
            )
    tracks.discard(None)
    tracks = sorted(tracks, key=lambda track: track.position or 0)
    result["tracks"] = [
        {
            "id": track.id,
            "name": track.name,
            "description": track.description,
            "color": track.color,
        }
        for track in tracks
    ]
    result["rooms"] = [
        {"id": room.id, "name": room.name, "description": room.description}
        for room in all_event_rooms
        if room in rooms
    ]
    include_avatar = schedule.event.cfp.request_avatar
    result["speakers"] = [
        {
            "code": speaker.code,
            "name": speaker.get_display_name(),
            "avatar": (
                speaker.get_avatar_url(event=schedule.event) or None
                if include_avatar
                else None
            ),
            "avatar_thumbnail_default": (
                speaker.profile_picture.get_avatar_url(
                    event=schedule.event, thumbnail="default"
                )
                if include_avatar and speaker.profile_picture_id
                else None
            ),
            "avatar_thumbnail_tiny": (
                speaker.profile_picture.get_avatar_url(
                    event=schedule.event, thumbnail="tiny"
                )
                if include_avatar and speaker.profile_picture_id
                else None
            ),
        }
        for speaker in speakers
    ]
    return result
