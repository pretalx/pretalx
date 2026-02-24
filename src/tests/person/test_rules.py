import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.person.rules import (
    can_mark_speakers_arrived,
    can_view_information,
    is_administrator,
    is_only_reviewer,
    is_reviewer,
)
from pretalx.submission.models.submission import SubmissionStates
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_admin", "expected"), ((True, True), (False, False)), ids=["admin", "non_admin"]
)
def test_is_administrator_matches_admin_flag(is_admin, expected):
    user = UserFactory(is_administrator=is_admin)
    assert is_administrator(user, None) is expected


def test_is_administrator_returns_false_for_none():
    assert is_administrator(None, None) is False


@pytest.mark.django_db
def test_is_reviewer_returns_true_for_reviewer():
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    assert is_reviewer(user, info) is True


@pytest.mark.django_db
def test_is_reviewer_returns_false_for_non_reviewer():
    event = EventFactory()
    user = UserFactory()

    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    assert is_reviewer(user, info) is False


@pytest.mark.django_db
@pytest.mark.parametrize("user", (None, AnonymousUser()), ids=["none", "anonymous"])
def test_is_reviewer_returns_false_for_invalid_user(user):
    event = EventFactory()
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)
    assert is_reviewer(user, info) is False


@pytest.mark.django_db
@pytest.mark.parametrize("obj", (None, object()), ids=["none_obj", "obj_without_event"])
def test_is_reviewer_returns_false_for_invalid_obj(obj):
    user = UserFactory()
    assert is_reviewer(user, obj) is False


@pytest.mark.django_db
def test_is_only_reviewer_returns_true_when_only_reviewer():
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=False,
        can_change_organiser_settings=False,
        can_change_teams=False,
        can_create_events=False,
    )
    team.members.add(user)

    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    assert is_only_reviewer(user, info) is True


@pytest.mark.django_db
def test_is_only_reviewer_returns_false_when_has_other_permissions():
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=True,
    )
    team.members.add(user)

    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    assert is_only_reviewer(user, info) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("from_delta", "to_delta", "expected"),
    ((0, 2, True), (10, 12, False), (-10, -5, False)),
    ids=["within_window", "before_window", "after_window"],
)
def test_can_mark_speakers_arrived_respects_event_window(
    from_delta, to_delta, expected
):
    """Window is (date_from - 3 days) through date_to."""
    today = now().date()
    event = EventFactory(
        date_from=today + dt.timedelta(days=from_delta),
        date_to=today + dt.timedelta(days=to_delta),
    )
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    assert can_mark_speakers_arrived(None, info) is expected


@pytest.mark.django_db
def test_can_view_information_submitters_without_submission():
    event = EventFactory()
    user = UserFactory()
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event, target_group="submitters")

    with scopes_disabled():
        assert can_view_information(user, info) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("target_group", "state", "expected"),
    (
        ("submitters", SubmissionStates.SUBMITTED, True),
        ("confirmed", SubmissionStates.CONFIRMED, True),
        ("confirmed", SubmissionStates.SUBMITTED, False),
        ("accepted", SubmissionStates.ACCEPTED, True),
        ("accepted", SubmissionStates.SUBMITTED, False),
    ),
)
def test_can_view_information_matches_target_group_to_submission_state(
    target_group, state, expected
):
    event = EventFactory()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=state)
        submission.speakers.add(speaker)
        info = SpeakerInformationFactory(event=event, target_group=target_group)

    with scopes_disabled():
        assert can_view_information(speaker.user, info) is expected


@pytest.mark.django_db
def test_can_view_information_limited_to_track():
    """Info limited to a specific track is visible only to speakers on that track."""
    event = EventFactory()
    with scopes_disabled():
        track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        submission.speakers.add(speaker)
        info = SpeakerInformationFactory(event=event, target_group="submitters")
        info.limit_tracks.add(track)

        other_speaker = SpeakerFactory(event=event)
        other_submission = SubmissionFactory(event=event, track=other_track)
        other_submission.speakers.add(other_speaker)

    with scopes_disabled():
        assert can_view_information(speaker.user, info) is True
        assert can_view_information(other_speaker.user, info) is False


@pytest.mark.django_db
def test_can_view_information_limited_to_type():
    """Info limited to a specific submission type is visible only to matching speakers."""
    event = EventFactory()
    with scopes_disabled():
        other_type = SubmissionTypeFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        info = SpeakerInformationFactory(event=event, target_group="submitters")
        info.limit_types.add(submission.submission_type)

        other_speaker = SpeakerFactory(event=event)
        other_submission = SubmissionFactory(event=event, submission_type=other_type)
        other_submission.speakers.add(other_speaker)

    with scopes_disabled():
        assert can_view_information(speaker.user, info) is True
        assert can_view_information(other_speaker.user, info) is False
