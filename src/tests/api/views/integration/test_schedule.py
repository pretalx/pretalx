# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.models import Schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ResourceFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def public_schedule_event(event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        slot = TalkSlotFactory(submission=role.submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    return event, slot


@pytest.fixture
def invisible_slot(public_schedule_event):
    event, _ = public_schedule_event
    with scopes_disabled():
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
        slot = event.current_schedule.talks.get(submission=sub)
        slot.is_visible = False
        slot.save()
        return slot


def test_schedule_anonymous_reads(client, public_schedule_event):
    event, _ = public_schedule_event
    with scopes_disabled():
        assert event.schedules.count() >= 2
        schedule = event.current_schedule

    listing = client.get(event.api_urls.schedules, follow=True)
    detail = client.get(event.api_urls.schedules + f"{schedule.pk}/", follow=True)
    latest = client.get(event.api_urls.schedules + "latest/")
    wip = client.get(event.api_urls.schedules + "wip/")

    assert listing.status_code == 200
    assert [s["id"] for s in listing.json()["results"]] == [schedule.pk]
    assert listing.json()["results"][0]["version"] == "v1"
    assert detail.status_code == 200
    assert detail.json()["id"] == schedule.pk
    assert detail.json()["version"] == "v1"
    assert latest.status_code == 200
    assert latest.json()["version"] == "v1"
    assert wip.status_code == 404


def test_schedule_list_anonymous_cannot_see_when_not_public(client):
    event = EventFactory(feature_flags={"show_schedule": False})

    response = client.get(event.api_urls.schedules, follow=True)

    assert response.status_code == 401


def test_schedule_orga_reads(client, orga_write_token, public_schedule_event):
    event, _ = public_schedule_event
    with scopes_disabled():
        total_schedules = event.schedules.count()
        assert total_schedules >= 2
    # Exporters count as actions, so they need the write token.
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    listing = client.get(event.api_urls.schedules, follow=True, headers=headers)
    wip = client.get(event.api_urls.schedules + "wip/", headers=headers)
    latest = client.get(event.api_urls.schedules + "latest/", headers=headers)
    exported = client.get(
        event.api_urls.schedules + "latest/exporters/schedule.json/", headers=headers
    )
    unknown_exporter = client.get(
        event.api_urls.schedules + "latest/exporters/nonexistent_format/",
        headers=headers,
    )

    assert listing.status_code == 200
    assert listing.json()["count"] == total_schedules
    assert wip.status_code == 200
    assert wip.json()["version"] == "wip"
    assert latest.status_code == 200
    assert latest.json()["version"] == "v1"
    assert exported.status_code == 200
    assert exported.json()["schedule"]["version"] == "v1"
    assert unknown_exporter.status_code == 404


def test_schedule_latest_shortcut_404_when_no_current_schedule(
    client, orga_read_token, event
):
    with scopes_disabled():
        Schedule.objects.filter(event=event).delete()
        event.current_schedule = None
        event.save()
        event.schedules.create(version=None)

    response = client.get(
        event.api_urls.schedules + "latest/",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 404


def test_schedule_redirect_version(client, public_schedule_event):
    event, _ = public_schedule_event
    url = event.api_urls.schedules + "by-version/"
    with scopes_disabled():
        schedule_url_suffix = f"/schedules/{event.current_schedule.pk}/"

    by_version = client.get(url + "?version=v1")
    by_latest = client.get(url + "?latest=true")
    nonexistent = client.get(url + "?version=nonexistent")
    missing = client.get(url)

    assert by_version.status_code == 200
    assert by_version["Content-Type"] == "text/plain"
    assert by_version.content.decode().endswith(schedule_url_suffix)
    assert by_latest.status_code == 200
    assert by_latest["Content-Type"] == "text/plain"
    assert by_latest.content.decode().endswith(schedule_url_suffix)
    assert nonexistent.status_code == 404
    assert missing.status_code == 404


def test_schedule_release_orga(client, orga_write_token, public_schedule_event):
    event, _ = public_schedule_event
    with scopes_disabled():
        initial_count = event.schedules.count()
    headers = {"Authorization": f"Token {orga_write_token.token}"}
    url = event.api_urls.schedules + "release/"

    response = client.post(
        url,
        data={"version": "v_new", "comment": "Test comment"},
        content_type="application/json",
        headers=headers,
    )
    duplicate = client.post(
        url, data={"version": "v1"}, content_type="application/json", headers=headers
    )
    missing_version = client.post(
        url,
        data={"comment": "No version"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["version"] == "v_new"
    with scopes_disabled():
        released = event.schedules.get(version="v_new")
        assert str(released.comment) == "Test comment"
        assert event.schedules.count() == initial_count + 1
    assert duplicate.status_code == 400
    assert "version" in duplicate.json()
    assert missing_version.status_code == 400
    assert "version" in missing_version.json()
    with scopes_disabled():
        assert event.schedules.count() == initial_count + 1


def test_schedule_release_readonly_token_denied(
    client, orga_read_token, public_schedule_event
):
    event, _ = public_schedule_event

    response = client.post(
        event.api_urls.schedules + "release/",
        data={"version": "v_readonly"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403


def test_schedule_expand_slots(client, public_schedule_event):
    event, slot = public_schedule_event
    with scopes_disabled():
        speaker = slot.submission.speakers.select_related("user").first()
        track = TrackFactory(event=event)
        slot.submission.track = track
        slot.submission.save()
    event.feature_flags["use_tracks"] = True
    event.save()

    response = client.get(
        event.api_urls.schedules
        + "latest/?expand=slots.room,slots.submission.speakers,"
        + "slots.submission.track,slots.submission.submission_type",
        follow=True,
    )

    assert response.status_code == 200
    data = response.json()
    assert [s["id"] for s in data["slots"]] == [slot.pk]
    expanded = data["slots"][0]
    assert expanded["room"]["id"] == slot.room_id
    assert expanded["room"]["name"]["en"] == slot.room.name
    assert expanded["submission"]["code"] == slot.submission.code
    assert expanded["submission"]["title"] == slot.submission.title
    assert [s["code"] for s in expanded["submission"]["speakers"]] == [speaker.code]
    assert expanded["submission"]["speakers"][0]["name"] == speaker.get_display_name()
    assert expanded["submission"]["track"]["name"]["en"] == track.name
    assert (
        expanded["submission"]["submission_type"]["name"]["en"]
        == slot.submission.submission_type.name
    )


@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_list_query_count(
    client, event, item_count, django_assert_num_queries, orga_read_token
):
    with scopes_disabled():
        for i in range(item_count):
            ScheduleFactory(event=event, version=f"v{i}")

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.schedules,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    # WIP schedule + item_count released ones
    assert data["count"] == item_count + 1


def test_slot_anonymous_reads(client, public_schedule_event):
    event, slot = public_schedule_event

    listing = client.get(event.api_urls.slots, follow=True)
    detail = client.get(event.api_urls.slots + f"{slot.pk}/", follow=True)
    ical = client.get(event.api_urls.slots + f"{slot.pk}/ical/", follow=True)

    assert listing.status_code == 200
    data = listing.json()
    assert [r["id"] for r in data["results"]] == [slot.pk]
    assert data["results"][0]["submission"] == slot.submission.code
    assert "is_visible" not in data["results"][0]
    assert detail.status_code == 200
    assert detail.json()["id"] == slot.pk
    assert detail.json()["submission"] == slot.submission.code
    assert "is_visible" not in detail.json()
    assert ical.status_code == 200
    assert ical["Content-Type"] == "text/calendar"
    content = ical.content.decode()
    assert "BEGIN:VCALENDAR" in content
    assert slot.submission.code in content
    assert (
        ical["Content-Disposition"]
        == f'attachment; filename="{event.slug}-{slot.submission.code}.ics"'
    )


def test_slot_invisible_hidden_from_anonymous_but_not_orga(
    client, orga_read_token, public_schedule_event, invisible_slot
):
    event, slot = public_schedule_event
    with scopes_disabled():
        visible_pk = (
            event.current_schedule.talks.filter(submission=slot.submission).first().pk
        )
    url = event.api_urls.slots + f"{invisible_slot.pk}/"

    listing = client.get(event.api_urls.slots, follow=True)
    detail = client.get(url, follow=True)
    ical = client.get(url + "ical/", follow=True)
    orga_detail = client.get(
        url, follow=True, headers={"Authorization": f"Token {orga_read_token.token}"}
    )

    assert listing.status_code == 200
    assert [r["id"] for r in listing.json()["results"]] == [visible_pk]
    assert detail.status_code == 404
    assert ical.status_code == 404
    assert orga_detail.status_code == 200
    assert orga_detail.json()["id"] == invisible_slot.pk


@pytest.mark.parametrize("item_count", (1, 3))
def test_slot_list_orga_default_current_schedule(
    client,
    orga_read_token,
    public_schedule_event,
    item_count,
    django_assert_num_queries,
):
    event, slot = public_schedule_event
    if item_count > 1:
        with scopes_disabled():
            for _ in range(item_count - 1):
                sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
                TalkSlotFactory(submission=sub, is_visible=False)
            with scope(event=event):
                freeze_schedule(event.wip_schedule, "v_extra", notify_speakers=False)

    with scopes_disabled():
        expected_ids = set(event.current_schedule.talks.values_list("pk", flat=True))

    with django_assert_num_queries(14):
        response = client.get(
            event.api_urls.slots,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(expected_ids)
    assert {r["id"] for r in data["results"]} == expected_ids


def test_slot_list_orga_filters(client, orga_read_token, public_schedule_event):
    event, slot = public_schedule_event
    with scopes_disabled():
        current_schedule_id = event.current_schedule.pk
        wip_pk = event.wip_schedule.pk
        wip_slot = event.wip_schedule.talks.get(submission=slot.submission)
        blocker = TalkSlotFactory(
            submission=None,
            room=RoomFactory(event=event),
            schedule=event.wip_schedule,
            is_visible=True,
            slot_type="blocker",
            start=event.datetime_from,
            end=event.datetime_from,
        )
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    by_schedule = client.get(
        f"{event.api_urls.slots}?schedule={current_schedule_id}",
        follow=True,
        headers=headers,
    )
    by_wip = client.get(
        f"{event.api_urls.slots}?schedule={wip_pk}", follow=True, headers=headers
    )
    by_submission = client.get(
        f"{event.api_urls.slots}?submission={slot.submission.code}",
        follow=True,
        headers=headers,
    )

    assert by_schedule.status_code == 200
    assert [r["id"] for r in by_schedule.json()["results"]] == [slot.pk]
    assert by_wip.status_code == 200
    assert {r["id"] for r in by_wip.json()["results"]} == {wip_slot.pk, blocker.pk}
    assert by_submission.status_code == 200
    assert {r["id"] for r in by_submission.json()["results"]} == {slot.pk, wip_slot.pk}
    assert all(
        r["submission"] == slot.submission.code for r in by_submission.json()["results"]
    )


def test_slot_break_slot_anonymous(client, public_schedule_event):
    event, _ = public_schedule_event
    with scopes_disabled():
        break_slot = TalkSlotFactory(
            submission=None,
            room=RoomFactory(event=event),
            schedule=event.current_schedule,
            is_visible=True,
            start=event.datetime_from,
            end=event.datetime_from,
        )

    detail = client.get(event.api_urls.slots + f"{break_slot.pk}/", follow=True)
    ical = client.get(event.api_urls.slots + f"{break_slot.pk}/ical/", follow=True)

    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == break_slot.pk
    assert data["submission"] is None
    assert data["room"] == break_slot.room_id
    assert ical.status_code == 404


def test_slot_update_readonly_token_denied(
    client, orga_read_token, public_schedule_event
):
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data={"room": None},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.room_id is not None


def test_slot_update_room_on_wip_schedule(
    client, orga_write_token, public_schedule_event
):
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()
        other_room = RoomFactory(event=event)
        assert wip_slot.room_id is not None
    initial_visibility = wip_slot.is_visible
    url = event.api_urls.slots + f"{wip_slot.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        data={"room": other_room.pk, "is_visible": not initial_visibility},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["is_visible"] == initial_visibility
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.room_id == other_room.pk
        assert wip_slot.is_visible == initial_visibility

    response = client.patch(
        url, data={"room": None}, content_type="application/json", headers=headers
    )

    assert response.status_code == 200
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.room_id is None

    released = client.patch(
        event.api_urls.slots + f"{slot.pk}/",
        data={"room": other_room.pk},
        content_type="application/json",
        headers=headers,
    )

    assert released.status_code == 403
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.room_id != other_room.pk


@pytest.mark.parametrize("has_submission", (True, False))
def test_slot_update_end_and_description_blocked_when_submission_exists(
    client, orga_write_token, public_schedule_event, has_submission
):
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()
        if not has_submission:
            wip_slot.submission = None
            wip_slot.save()

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data={"description": "test desc", "end": wip_slot.end.isoformat()},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    if has_submission:
        assert response.status_code == 400
        data = response.json()
        assert "end" in data
        assert "description" in data
    else:
        assert response.status_code == 200
        assert response.json()["description"]["en"] == "test desc"


def test_slot_expand_parameters(client, orga_read_token, public_schedule_event):
    event, slot = public_schedule_event
    with scopes_disabled():
        speaker = slot.submission.speakers.select_related("user").first()
        track = TrackFactory(event=event)
        slot.submission.track = track
        slot.submission.save()
    event.feature_flags["use_tracks"] = True
    event.save()
    headers = {"Authorization": f"Token {orga_read_token.token}"}
    expand = (
        "room,schedule,submission,submission.speakers,submission.resources,"
        "submission.track,submission.submission_type"
    )

    plain = client.get(event.api_urls.slots + f"{slot.pk}/", headers=headers)
    detail = client.get(
        event.api_urls.slots + f"{slot.pk}/", {"expand": expand}, headers=headers
    )
    listing = client.get(event.api_urls.slots, {"expand": expand}, headers=headers)

    assert plain.status_code == 200
    data = plain.json()
    assert data["submission"] == slot.submission.code
    assert data["room"] == slot.room_id
    assert data["schedule"] == slot.schedule_id
    assert detail.status_code == 200
    data = detail.json()
    assert data["room"]["id"] == slot.room_id
    assert data["schedule"]["id"] == slot.schedule_id
    assert data["submission"]["code"] == slot.submission.code
    assert [s["code"] for s in data["submission"]["speakers"]] == [speaker.code]
    assert data["submission"]["track"]["name"]["en"] == track.name
    assert (
        data["submission"]["submission_type"]["name"]["en"]
        == slot.submission.submission_type.name
    )
    assert listing.status_code == 200
    assert [r["id"] for r in listing.json()["results"]] == [slot.pk]
    assert listing.json()["results"][0]["submission"] == data["submission"]


def test_slot_orga_sees_blocker_in_wip(client, orga_read_token, event):
    with scopes_disabled():
        room = RoomFactory(event=event)
        blocker = TalkSlotFactory(
            submission=None,
            room=room,
            schedule=event.wip_schedule,
            is_visible=True,
            slot_type="blocker",
            start=event.datetime_from,
            end=event.datetime_from,
        )
        wip_pk = event.wip_schedule.pk

    response = client.get(
        f"{event.api_urls.slots}?schedule={wip_pk}",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [blocker.pk]


@pytest.mark.parametrize("item_count", (1, 3))
def test_slot_list_query_count(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        for _ in range(item_count):
            sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
            TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    with django_assert_num_queries(8):
        response = client.get(event.api_urls.slots, follow=True)

    assert response.status_code == 200
    assert response.json()["count"] == item_count


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.parametrize(
    "expand", ("slots,slots.submission", "slots,slots.submission.speakers")
)
def test_schedule_expanded_submissions_query_count(
    client, event, item_count, expand, django_assert_num_queries
):
    public_resources = set()
    with scopes_disabled():
        tag = TagFactory(event=event, is_public=True)
        for _ in range(item_count):
            role = SpeakerRoleFactory(
                submission__event=event,
                submission__state=SubmissionStates.CONFIRMED,
                speaker__event=event,
            )
            role.submission.tags.add(tag)
            public_resources.add(ResourceFactory(submission=role.submission).pk)
            ResourceFactory(submission=role.submission, is_public=False)
            TalkSlotFactory(submission=role.submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    with django_assert_num_queries(9):
        response = client.get(
            event.api_urls.schedules + f"latest/?expand={expand}", follow=True
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["slots"]) == item_count
    for slot in data["slots"]:
        assert len(slot["submission"]["speakers"]) == 1
        assert slot["submission"]["tags"] == [tag.pk]
    returned = {pk for slot in data["slots"] for pk in slot["submission"]["resources"]}
    assert returned == public_resources


@pytest.mark.parametrize("token_fixture", ("orga_read_token", "review_token"))
def test_expanded_internals_visible_to_orga_and_reviewers(
    client, event, token_fixture, request
):
    token = request.getfixturevalue(token_fixture)
    with scopes_disabled():
        tag = TagFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.tags.add(tag)
        resource = ResourceFactory(submission=submission, is_public=False)
        TalkSlotFactory(submission=submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    headers = {"Authorization": f"Token {token.token}"}

    schedule = client.get(
        event.api_urls.schedules + "latest/?expand=slots,slots.submission",
        follow=True,
        headers=headers,
    )
    slots = client.get(
        event.api_urls.slots + "?expand=submission", follow=True, headers=headers
    )

    assert schedule.status_code == 200
    data = schedule.json()["slots"][0]["submission"]
    assert data["tags"] == [tag.pk]
    assert data["resources"] == [resource.pk]
    assert slots.status_code == 200
    assert slots.json()["results"][0]["submission"] == data


def test_schedule_expanded_tags_anonymous_sees_only_public_ones(client, event):
    with scopes_disabled():
        public_tag = TagFactory(event=event, is_public=True)
        internal_tag = TagFactory(event=event, is_public=False)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.tags.add(public_tag, internal_tag)
        TalkSlotFactory(submission=submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(
        event.api_urls.schedules
        + "latest/?expand=slots,slots.submission,slots.submission.tags",
        follow=True,
    )

    assert response.status_code == 200
    tags = response.json()["slots"][0]["submission"]["tags"]
    assert [tag["id"] for tag in tags] == [public_tag.pk]


@pytest.mark.parametrize("item_count", (1, 3))
def test_slot_list_expanded_submissions_query_count(
    client, event, item_count, django_assert_num_queries
):
    public_resources = set()
    with scopes_disabled():
        tag = TagFactory(event=event, is_public=True)
        for _ in range(item_count):
            role = SpeakerRoleFactory(
                submission__event=event,
                submission__state=SubmissionStates.CONFIRMED,
                speaker__event=event,
            )
            role.submission.tags.add(tag)
            public_resources.add(ResourceFactory(submission=role.submission).pk)
            ResourceFactory(submission=role.submission, is_public=False)
            TalkSlotFactory(submission=role.submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    with django_assert_num_queries(10):
        response = client.get(event.api_urls.slots + "?expand=submission", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count
    for result in data["results"]:
        assert len(result["submission"]["speakers"]) == 1
        assert result["submission"]["tags"] == [tag.pk]
    returned = {
        pk for result in data["results"] for pk in result["submission"]["resources"]
    }
    assert returned == public_resources


def test_slot_expanded_speakers_keep_their_order(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        second = SpeakerRoleFactory(
            submission=submission, speaker__event=event, position=1
        )
        first = SpeakerRoleFactory(
            submission=submission, speaker__event=event, position=0
        )
        TalkSlotFactory(submission=submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(
        event.api_urls.slots + "?expand=submission,submission.speakers", follow=True
    )

    assert response.status_code == 200
    speakers = response.json()["results"][0]["submission"]["speakers"]
    assert [s["code"] for s in speakers] == [first.speaker.code, second.speaker.code]
