import pytest
from django_scopes import scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
    UserApiTokenFactory,
    UserFactory,
)


@pytest.fixture
def orga_user_token(organiser_user):
    """Read-only API token for the organiser user."""
    token = UserApiTokenFactory(user=organiser_user)
    token.events.set(organiser_user.get_events_with_any_permission())
    token.endpoints = {key: ["list", "retrieve"] for key in ENDPOINTS}
    token.save()
    return token


@pytest.fixture
def orga_user_write_token(organiser_user):
    """Read-write API token for the organiser user."""
    token = UserApiTokenFactory(user=organiser_user)
    token.events.set(organiser_user.get_events_with_any_permission())
    token.endpoints = {
        key: ["list", "retrieve", "create", "update", "destroy", "actions"]
        for key in ENDPOINTS
    }
    token.save()
    return token


@pytest.fixture
def review_user(event):
    """User with reviewer-only access to the event."""
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            can_change_submissions=False,
            is_reviewer=True,
        )
        team.members.add(user)
    return user


@pytest.fixture
def submission(event):
    """A submitted submission with one speaker on the test event."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    return sub


@pytest.fixture
def other_submission(event):
    """A second submission on the same event with a different speaker."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    return sub


@pytest.fixture
def accepted_submission(event):
    """An accepted submission with a speaker."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        sub.accept()
    return sub


@pytest.fixture
def rejected_submission(event):
    """A rejected submission with a speaker."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        sub.reject()
    return sub


@pytest.fixture
def tag(event):
    """A tag on the test event."""
    return TagFactory(event=event)


@pytest.fixture
def track(event):
    """A track on the test event (enables use_tracks feature flag)."""
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
    return TrackFactory(event=event)


@pytest.fixture
def submission_type(event):
    """An additional submission type for the event."""
    return SubmissionTypeFactory(event=event, name="Workshop", default_duration=60)
