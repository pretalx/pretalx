import json

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.schedule.models import Schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def public_schedule_event(event):
    """A public event with a released schedule, a visible slot, and show_schedule=True.

    Returns (event, published_slot) — the slot lives on event.current_schedule.
    """
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        slot = TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)
    return event, slot


@pytest.fixture
def invisible_slot(public_schedule_event):
    """An additional invisible slot on the released schedule.

    Freeze recalculates is_visible from submission state, so we mark the
    resulting slot invisible after freeze to simulate a hidden talk."""
    event, _ = public_schedule_event
    with scopes_disabled():
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v2", notify_speakers=False)
        slot = event.current_schedule.talks.get(submission=sub)
        slot.is_visible = False
        slot.save()
        return slot


@pytest.mark.django_db
def test_schedule_list_anonymous_sees_only_current(client, public_schedule_event):
    """Anonymous users see only the released (current) schedule, not the WIP one."""
    event, _ = public_schedule_event
    with scopes_disabled():
        assert event.schedules.count() >= 2

    response = client.get(event.api_urls.schedules, follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["version"] is not None


@pytest.mark.django_db
def test_schedule_list_anonymous_cannot_see_when_not_public(client, event):
    """Anonymous users get 401 when the event has show_schedule=False."""
    event.is_public = True
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(event.api_urls.schedules, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_schedule_list_orga_sees_all(client, orga_token, public_schedule_event):
    """Organisers see all schedules including WIP."""
    event, _ = public_schedule_event
    with scopes_disabled():
        total_schedules = event.schedules.count()
        assert total_schedules >= 2

    response = client.get(
        event.api_urls.schedules,
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == total_schedules


@pytest.mark.django_db
def test_schedule_list_orga_sees_all_when_not_public(
    client, orga_token, public_schedule_event
):
    """Organisers see schedules even when event has show_schedule=False."""
    event, _ = public_schedule_event
    event.feature_flags["show_schedule"] = False
    event.save()
    with scopes_disabled():
        total_schedules = event.schedules.count()

    response = client.get(
        event.api_urls.schedules,
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == total_schedules


@pytest.mark.django_db
def test_schedule_wip_shortcut_orga_can_access(
    client, orga_token, public_schedule_event
):
    """Organisers can retrieve the WIP schedule via /wip/."""
    event, _ = public_schedule_event

    response = client.get(
        event.api_urls.schedules + "wip/",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "wip"


@pytest.mark.django_db
def test_schedule_wip_shortcut_anonymous_cannot_access(client, public_schedule_event):
    """Anonymous users get 404 for the WIP shortcut."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.schedules + "wip/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_retrieve_by_pk(client, public_schedule_event):
    """Retrieving a schedule by its numeric PK works for anonymous users on public events."""
    event, _ = public_schedule_event
    with scopes_disabled():
        schedule = event.current_schedule

    response = client.get(event.api_urls.schedules + f"{schedule.pk}/", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == schedule.pk
    assert data["version"] == schedule.version


@pytest.mark.django_db
def test_schedule_latest_shortcut_orga_can_access(
    client, orga_token, public_schedule_event
):
    """Organisers can retrieve the latest schedule via /latest/."""
    event, _ = public_schedule_event

    response = client.get(
        event.api_urls.schedules + "latest/",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    with scopes_disabled():
        assert data["version"] == event.current_schedule.version


@pytest.mark.django_db
def test_schedule_latest_shortcut_anonymous_public(client, public_schedule_event):
    """Anonymous users can access /latest/ when the event is public with show_schedule."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.schedules + "latest/")

    assert response.status_code == 200
    data = response.json()
    with scopes_disabled():
        assert data["version"] == event.current_schedule.version


@pytest.mark.django_db
def test_schedule_latest_shortcut_anonymous_schedule_not_public(
    client, public_schedule_event
):
    """Anonymous users get 401 for /latest/ when show_schedule=False."""
    event, _ = public_schedule_event
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(event.api_urls.schedules + "latest/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_schedule_latest_shortcut_anonymous_event_not_public(
    client, public_schedule_event
):
    """Anonymous users get 401 for /latest/ when event is not public."""
    event, _ = public_schedule_event
    event.is_public = False
    event.save()

    response = client.get(event.api_urls.schedules + "latest/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_schedule_latest_shortcut_404_when_no_current_schedule(
    client, orga_token, event
):
    """Both orga and anonymous get 404 for /latest/ when no schedule is released."""
    with scopes_disabled():
        Schedule.objects.filter(event=event).delete()
        event.current_schedule = None
        event.save()
        event.schedules.create(version=None)

    response = client.get(
        event.api_urls.schedules + "latest/",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_redirect_version_success(client, public_schedule_event):
    """by-version returns a plain-text URL pointing to the correct schedule."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.schedules + "by-version/?version=v1")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain"
    url = response.content.decode()
    with scopes_disabled():
        assert url.endswith(f"/schedules/{event.current_schedule.pk}/")


@pytest.mark.django_db
def test_schedule_redirect_version_nonexistent(client, public_schedule_event):
    """by-version returns 404 for a version that doesn't exist."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.schedules + "by-version/?version=nonexistent")

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_redirect_version_latest_param(client, public_schedule_event):
    """by-version with ?latest=true returns the current schedule URL."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.schedules + "by-version/?latest=true")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain"
    url = response.content.decode()
    with scopes_disabled():
        assert url.endswith(f"/schedules/{event.current_schedule.pk}/")


@pytest.mark.django_db
def test_schedule_redirect_version_missing_query_param(client, public_schedule_event):
    """by-version without version or latest param returns 404."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.schedules + "by-version/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_redirect_version_anonymous_denied_when_not_public(
    client, public_schedule_event
):
    """by-version returns 401 for anonymous users when show_schedule=False."""
    event, _ = public_schedule_event
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(
        event.api_urls.schedules + "by-version/?version=v1", follow=True
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_schedule_release_orga_success(client, orga_write_token, public_schedule_event):
    """Organiser with write token can release a new schedule version."""
    event, _ = public_schedule_event
    with scopes_disabled():
        initial_count = event.schedules.count()

    response = client.post(
        event.api_urls.schedules + "release/",
        data=json.dumps({"version": "v_new", "comment": "Test comment"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["version"] == "v_new"
    with scopes_disabled():
        released = event.schedules.get(version="v_new")
        assert str(released.comment) == "Test comment"
        assert event.schedules.count() == initial_count + 1


@pytest.mark.django_db
def test_schedule_release_duplicate_version_fails(
    client, orga_write_token, public_schedule_event
):
    """Releasing with an already-used version name returns 400."""
    event, _ = public_schedule_event

    response = client.post(
        event.api_urls.schedules + "release/",
        data=json.dumps({"version": "v1"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "version" in response.json()


@pytest.mark.django_db
def test_schedule_release_missing_version_fails(
    client, orga_write_token, public_schedule_event
):
    """Releasing without a version name returns 400."""
    event, _ = public_schedule_event

    response = client.post(
        event.api_urls.schedules + "release/",
        data=json.dumps({"comment": "No version"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "version" in response.json()


@pytest.mark.django_db
def test_schedule_release_anonymous_denied(client, public_schedule_event):
    """Anonymous users cannot release a schedule (401)."""
    event, _ = public_schedule_event

    response = client.post(
        event.api_urls.schedules + "release/",
        data=json.dumps({"version": "v_anon"}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_schedule_release_readonly_token_denied(
    client, orga_token, public_schedule_event
):
    """Read-only token cannot release a schedule (403)."""
    event, _ = public_schedule_event

    response = client.post(
        event.api_urls.schedules + "release/",
        data=json.dumps({"version": "v_readonly"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_schedule_exporter_orga_access(client, orga_write_token, public_schedule_event):
    """Organisers can access schedule exporters via /latest/exporters/schedule.json/."""
    event, _ = public_schedule_event

    response = client.get(
        event.api_urls.schedules + "latest/exporters/schedule.json/",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    with scopes_disabled():
        assert data["schedule"]["version"] == event.current_schedule.version


@pytest.mark.django_db
def test_schedule_exporter_invalid_name(
    client, orga_write_token, public_schedule_event
):
    """Requesting a non-existent exporter returns 404."""
    event, _ = public_schedule_event

    response = client.get(
        event.api_urls.schedules + "latest/exporters/nonexistent_format/",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_expand_slots(client, public_schedule_event):
    """Expanding slots on /latest/ returns nested slot and submission data."""
    event, slot = public_schedule_event
    with scopes_disabled():
        speaker = slot.submission.speakers.first()

    response = client.get(
        event.api_urls.schedules
        + "latest/?expand=slots.room,slots.submission.speakers",
        follow=True,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["slots"], list)
    assert len(data["slots"]) == 1
    expanded = data["slots"][0]
    assert expanded["id"] == slot.pk
    assert isinstance(expanded["room"], dict)
    assert expanded["room"]["id"] == slot.room_id
    assert expanded["room"]["name"]["en"] == slot.room.name
    assert isinstance(expanded["submission"], dict)
    assert expanded["submission"]["code"] == slot.submission.code
    assert expanded["submission"]["title"] == slot.submission.title
    assert isinstance(expanded["submission"]["speakers"], list)
    assert expanded["submission"]["speakers"][0]["code"] == speaker.code
    assert expanded["submission"]["speakers"][0]["name"] == speaker.get_display_name()


@pytest.mark.django_db
def test_schedule_expand_slots_with_track_and_type(client, public_schedule_event):
    """Expanding submission.track and submission.submission_type returns nested data."""
    event, slot = public_schedule_event
    with scopes_disabled():
        track = TrackFactory(event=event)
        slot.submission.track = track
        slot.submission.save()
    event.feature_flags["use_tracks"] = True
    event.save()

    response = client.get(
        event.api_urls.schedules
        + "latest/?expand=slots.submission.track,slots.submission.submission_type",
        follow=True,
    )

    assert response.status_code == 200
    data = response.json()
    expanded = next(s for s in data["slots"] if s["id"] == slot.pk)
    assert expanded["submission"]["track"]["name"]["en"] == track.name
    assert (
        expanded["submission"]["submission_type"]["name"]["en"]
        == slot.submission.submission_type.name
    )


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_list_query_count(
    client, event, item_count, django_assert_num_queries, orga_token
):
    """Query count for schedule list is constant regardless of schedule count."""
    with scopes_disabled():
        for i in range(item_count):
            ScheduleFactory(event=event, version=f"v{i}")

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.schedules,
            follow=True,
            headers={"Authorization": f"Token {orga_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    # WIP schedule + item_count released ones
    assert data["count"] == item_count + 1


@pytest.mark.django_db
def test_slot_list_anonymous_current_schedule_only(client, public_schedule_event):
    """Anonymous users see only slots from the current schedule by default."""
    event, slot = public_schedule_event

    response = client.get(event.api_urls.slots, follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["id"] == slot.pk
    assert data["results"][0]["submission"] == slot.submission.code
    assert "is_visible" not in data["results"][0]


@pytest.mark.django_db
def test_slot_list_anonymous_only_visible(
    client, public_schedule_event, invisible_slot
):
    """Anonymous users see only visible slots, even when invisible ones exist."""
    event, slot = public_schedule_event
    with scopes_disabled():
        visible_pk = (
            event.current_schedule.talks.filter(submission=slot.submission).first().pk
        )

    response = client.get(event.api_urls.slots, follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["id"] == visible_pk


@pytest.mark.django_db
def test_slot_list_anonymous_event_not_public(client, event):
    """Anonymous users get 401 when event is not public."""
    event.is_public = False
    event.save()

    response = client.get(event.api_urls.slots, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_slot_list_anonymous_schedule_not_public(client, event):
    """Anonymous users get 401 when show_schedule is False."""
    event.is_public = True
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(event.api_urls.slots, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_slot_list_orga_default_current_schedule(
    client, orga_token, public_schedule_event, item_count, django_assert_num_queries
):
    """Orga sees all slots in the current schedule by default, including invisible ones."""
    event, slot = public_schedule_event
    if item_count > 1:
        with scopes_disabled():
            for _ in range(item_count - 1):
                sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
                TalkSlotFactory(submission=sub, is_visible=False)
            with scope(event=event):
                event.wip_schedule.freeze("v_extra", notify_speakers=False)

    with scopes_disabled():
        expected_ids = set(event.current_schedule.talks.values_list("pk", flat=True))

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.slots,
            follow=True,
            headers={"Authorization": f"Token {orga_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(expected_ids)
    assert {r["id"] for r in data["results"]} == expected_ids


@pytest.mark.django_db
def test_slot_list_orga_filter_by_schedule(client, orga_token, public_schedule_event):
    """Orga can filter slots by schedule PK, seeing slots across multiple schedules."""
    event, slot = public_schedule_event
    with scopes_disabled():
        current_schedule_id = event.current_schedule.pk

    response = client.get(
        f"{event.api_urls.slots}?schedule={current_schedule_id}",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    with scopes_disabled():
        expected_count = event.current_schedule.talks.count()
    assert data["count"] == expected_count
    assert slot.pk in [r["id"] for r in data["results"]]


@pytest.mark.django_db
def test_slot_list_orga_filter_by_submission(client, orga_token, public_schedule_event):
    """Orga can filter slots by submission code, getting all versions of that slot.

    The submission has slots on both the released v1 schedule and the WIP schedule."""
    event, slot = public_schedule_event

    response = client.get(
        f"{event.api_urls.slots}?submission={slot.submission.code}",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert all(r["submission"] == slot.submission.code for r in data["results"])


@pytest.mark.django_db
def test_slot_retrieve_anonymous_visible(client, public_schedule_event):
    """Anonymous users can retrieve a visible slot on a public event."""
    event, slot = public_schedule_event

    response = client.get(event.api_urls.slots + f"{slot.pk}/", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == slot.pk
    assert data["submission"] == slot.submission.code
    assert "is_visible" not in data


@pytest.mark.django_db
def test_slot_retrieve_anonymous_not_visible(
    client, public_schedule_event, invisible_slot
):
    """Anonymous users get 404 for an invisible slot."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.slots + f"{invisible_slot.pk}/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_slot_retrieve_anonymous_schedule_not_public(client, public_schedule_event):
    """Anonymous users get 401 when show_schedule=False."""
    event, slot = public_schedule_event
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(event.api_urls.slots + f"{slot.pk}/", follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_slot_retrieve_orga_sees_invisible(
    client, orga_token, public_schedule_event, invisible_slot
):
    """Organisers can see invisible slots."""
    event, _ = public_schedule_event

    response = client.get(
        event.api_urls.slots + f"{invisible_slot.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == invisible_slot.pk


@pytest.mark.django_db
def test_slot_retrieve_break_slot_anonymous(client, public_schedule_event):
    """Anonymous users can see a break slot (no submission) on the current schedule."""
    event, _ = public_schedule_event
    with scopes_disabled():
        break_slot = TalkSlotFactory(
            submission=None,
            room=RoomFactory(event=event),
            schedule=event.current_schedule,
            is_visible=True,
        )
        break_slot.start = event.datetime_from
        break_slot.end = event.datetime_from
        break_slot.save()

    response = client.get(event.api_urls.slots + f"{break_slot.pk}/", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == break_slot.pk
    assert data["submission"] is None
    assert data["room"] == break_slot.room_id


@pytest.mark.django_db
def test_slot_retrieve_break_slot_orga(client, orga_token, public_schedule_event):
    """Organisers can see a break slot on the current schedule."""
    event, _ = public_schedule_event
    with scopes_disabled():
        break_slot = TalkSlotFactory(
            submission=None,
            room=RoomFactory(event=event),
            schedule=event.current_schedule,
            is_visible=True,
        )
        break_slot.start = event.datetime_from
        break_slot.end = event.datetime_from
        break_slot.save()

    response = client.get(
        event.api_urls.slots + f"{break_slot.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == break_slot.pk
    assert data["submission"] is None


@pytest.mark.django_db
def test_slot_retrieve_nonexistent(client, public_schedule_event):
    """Retrieving a non-existent slot returns 404."""
    event, _ = public_schedule_event

    response = client.get(event.api_urls.slots + "99999/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_slot_update_anonymous_denied(client, public_schedule_event):
    """Anonymous users cannot update slots (401)."""
    event, slot = public_schedule_event

    response = client.patch(
        event.api_urls.slots + f"{slot.pk}/",
        data=json.dumps({"room": None}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_slot_update_readonly_token_denied(client, orga_token, public_schedule_event):
    """Read-only token cannot update slots (403)."""
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data=json.dumps({"room": None}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.room is not None


@pytest.mark.django_db
def test_slot_update_change_room(client, orga_write_token, public_schedule_event):
    """Orga with write token can change a WIP slot's room."""
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()
        other_room = RoomFactory(event=event)

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data=json.dumps({"room": other_room.pk}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.room == other_room


@pytest.mark.django_db
def test_slot_update_clear_room(client, orga_write_token, public_schedule_event):
    """Orga with write token can clear a WIP slot's room to None."""
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()
        assert wip_slot.room is not None

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data=json.dumps({"room": None}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.room is None


@pytest.mark.django_db
def test_slot_update_visibility_is_readonly(
    client, orga_write_token, public_schedule_event
):
    """is_visible cannot be changed via the API; the field is read-only."""
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()
    initial = wip_slot.is_visible

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data=json.dumps({"is_visible": not initial}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["is_visible"] == initial
    with scopes_disabled():
        wip_slot.refresh_from_db()
        assert wip_slot.is_visible == initial


@pytest.mark.django_db
def test_slot_update_non_wip_schedule_denied(
    client, orga_write_token, public_schedule_event
):
    """Slots on released (non-WIP) schedules cannot be updated (403)."""
    event, slot = public_schedule_event
    with scopes_disabled():
        other_room = RoomFactory(event=event)
    assert slot.schedule.version is not None

    response = client.patch(
        event.api_urls.slots + f"{slot.pk}/",
        data=json.dumps({"room": other_room.pk}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("has_submission", (True, False))
@pytest.mark.django_db
def test_slot_update_end_and_description_blocked_when_submission_exists(
    client, orga_write_token, public_schedule_event, has_submission
):
    """end and description can only be edited on slots without a submission.

    Slots with a submission must change those via the submission itself."""
    event, slot = public_schedule_event
    with scopes_disabled():
        wip_slot = event.wip_schedule.talks.filter(submission=slot.submission).first()
        if not has_submission:
            wip_slot.submission = None
            wip_slot.save()

    response = client.patch(
        event.api_urls.slots + f"{wip_slot.pk}/",
        data=json.dumps({"description": "test desc", "end": wip_slot.end.isoformat()}),
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


@pytest.mark.django_db
def test_slot_expand_parameters(client, orga_token, public_schedule_event):
    """Expanding room, schedule, and submission returns nested objects."""
    event, slot = public_schedule_event
    with scopes_disabled():
        speaker = slot.submission.speakers.first()

    response = client.get(
        event.api_urls.slots + f"{slot.pk}/",
        headers={"Authorization": f"Token {orga_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["submission"] == slot.submission.code
    assert data["room"] == slot.room_id
    assert data["schedule"] == slot.schedule_id

    response = client.get(
        event.api_urls.slots
        + f"{slot.pk}/?expand=room,schedule,submission,submission.speakers",
        headers={"Authorization": f"Token {orga_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data["room"], dict)
    assert data["room"]["id"] == slot.room_id

    assert isinstance(data["submission"], dict)
    assert data["submission"]["code"] == slot.submission.code

    assert isinstance(data["submission"]["speakers"], list)
    assert data["submission"]["speakers"][0]["code"] == speaker.code


@pytest.mark.django_db
def test_slot_expand_submission_track_and_type(
    client, orga_token, public_schedule_event
):
    """Expanding submission.track and submission.submission_type on slots endpoint
    triggers select_related in TalkSlotViewSet.get_queryset."""
    event, slot = public_schedule_event
    with scopes_disabled():
        track = TrackFactory(event=event)
        slot.submission.track = track
        slot.submission.save()
    event.feature_flags["use_tracks"] = True
    event.save()

    response = client.get(
        event.api_urls.slots + f"{slot.pk}/",
        {"expand": "submission.track,submission.submission_type"},
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["submission"], dict)
    assert data["submission"]["track"]["name"]["en"] == track.name
    assert (
        data["submission"]["submission_type"]["name"]["en"]
        == slot.submission.submission_type.name
    )


@pytest.mark.django_db
def test_slot_list_expand_submission_speakers(
    client, orga_token, public_schedule_event
):
    """Expanding submission.speakers on the list endpoint triggers
    prefetch_related in TalkSlotViewSet.get_queryset."""
    event, slot = public_schedule_event
    with scopes_disabled():
        speaker = slot.submission.speakers.first()

    response = client.get(
        event.api_urls.slots,
        {"expand": "submission.speakers,submission.resources"},
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    result = data["results"][0]
    assert isinstance(result["submission"], dict)
    assert result["submission"]["code"] == slot.submission.code
    assert isinstance(result["submission"]["speakers"], list)
    assert result["submission"]["speakers"][0]["code"] == speaker.code


@pytest.mark.django_db
def test_slot_ical_success(client, public_schedule_event):
    """The iCal endpoint returns a calendar file with the slot's submission."""
    event, slot = public_schedule_event

    response = client.get(event.api_urls.slots + f"{slot.pk}/ical/", follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar"
    content = response.content.decode()
    assert "BEGIN:VCALENDAR" in content
    assert slot.submission.code in content
    expected_disposition = (
        f'attachment; filename="{event.slug}-{slot.submission.code}.ics"'
    )
    assert response["Content-Disposition"] == expected_disposition


@pytest.mark.django_db
def test_slot_ical_not_visible(client, public_schedule_event, invisible_slot):
    """The iCal endpoint returns 404 for an invisible slot."""
    event, _ = public_schedule_event

    response = client.get(
        event.api_urls.slots + f"{invisible_slot.pk}/ical/", follow=True
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_slot_ical_no_submission(client, public_schedule_event):
    """The iCal endpoint returns 404 for a slot without a submission (break)."""
    event, _ = public_schedule_event
    with scopes_disabled():
        break_slot = TalkSlotFactory(
            submission=None,
            room=RoomFactory(event=event),
            schedule=event.current_schedule,
            is_visible=True,
        )
        break_slot.start = event.datetime_from
        break_slot.end = event.datetime_from
        break_slot.save()

    response = client.get(event.api_urls.slots + f"{break_slot.pk}/ical/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_slot_ical_schedule_not_public(client, public_schedule_event):
    """iCal returns 401 when show_schedule=False."""
    event, slot = public_schedule_event
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(event.api_urls.slots + f"{slot.pk}/ical/", follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_slot_ical_event_not_public(client, public_schedule_event):
    """iCal returns 401 when event is not public."""
    event, slot = public_schedule_event
    event.is_public = False
    event.save()

    response = client.get(event.api_urls.slots + f"{slot.pk}/ical/", follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_slot_orga_sees_blocker_in_wip(client, orga_token, event):
    """Organisers can see blocker-type slots in the WIP schedule."""
    with scopes_disabled():
        room = RoomFactory(event=event)
        blocker = TalkSlotFactory(
            submission=None, room=room, schedule=event.wip_schedule, is_visible=True
        )
        blocker.slot_type = "blocker"
        blocker.start = event.datetime_from
        blocker.end = event.datetime_from
        blocker.save()
        wip_pk = event.wip_schedule.pk

    response = client.get(
        f"{event.api_urls.slots}?schedule={wip_pk}",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert blocker.pk in [r["id"] for r in data["results"]]


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_slot_list_query_count(client, event, item_count, django_assert_num_queries):
    """Query count for the slot list is constant regardless of slot count."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        for _ in range(item_count):
            sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
            TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(7):
        response = client.get(event.api_urls.slots, follow=True)

    assert response.status_code == 200
    assert response.json()["count"] == item_count
