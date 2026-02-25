import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils.timezone import now
from django_scopes import scopes_disabled
from faker import Faker

from pretalx.common.management.commands.create_test_event import Command, schedule_slot
from pretalx.event.models import Event
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import Review
from tests.factories.person import UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_schedule_slot_sets_start_end_room(talk_slot):
    with scopes_disabled():
        submission = talk_slot.submission
        room = talk_slot.room
        new_time = submission.event.datetime_from + dt.timedelta(hours=2)
        expected_end = new_time + dt.timedelta(
            minutes=submission.submission_type.default_duration
        )

        schedule_slot(submission, new_time, room)
        talk_slot.refresh_from_db()

        assert talk_slot.start == new_time
        assert talk_slot.end == expected_end
        assert talk_slot.room == room


@pytest.mark.django_db
def test_create_user_with_retry_creates_user():
    cmd = Command(stdout=StringIO(), stderr=StringIO())

    user = cmd.create_user_with_retry(name="Test User", email_base="fresh@example.org")

    assert user.name == "Test User"
    assert user.email == "fresh@example.org"


@pytest.mark.django_db
def test_create_user_with_retry_retries_on_duplicate_email():
    User.objects.create_user(name="Existing", email="taken@example.org")
    cmd = Command(stdout=StringIO(), stderr=StringIO())

    user = cmd.create_user_with_retry(name="New User", email_base="taken@example.org")

    assert user.name == "New User"
    assert user.email == "taken1@example.org"


@pytest.mark.django_db
def test_create_user_with_retry_exhausts_retries_raises():
    """When all retry attempts result in IntegrityError, the last one propagates."""
    cmd = Command(stdout=StringIO(), stderr=StringIO())
    for i in range(3):
        email = "clash@example.org" if i == 0 else f"clash{i}@example.org"
        User.objects.create_user(name=f"Blocker {i}", email=email)

    with pytest.raises(IntegrityError):
        cmd.create_user_with_retry(
            name="Unlucky", email_base="clash@example.org", max_retries=3
        )


@pytest.mark.django_db
def test_build_event_without_admin_returns_none():
    cmd = Command(stdout=StringIO(), stderr=StringIO())

    result = cmd.build_event("schedule", "test-slug")

    assert result is None


@pytest.mark.django_db
@pytest.mark.parametrize("stage", ("cfp", "review", "schedule", "over"))
def test_create_test_event_end_to_end(stage):
    UserFactory(is_administrator=True)
    slug = f"demo-{stage}"

    call_command("create_test_event", stage=stage, slug=slug, seed="42")

    with scopes_disabled():
        event = Event.objects.get(slug=slug)
        assert event.name == "DemoCon"
        assert event.rooms.count() == 2
        assert event.tracks.count() >= 2
        assert event.cfp is not None
        submissions = event.submissions.all()
        assert submissions.count() > 0

        if stage == "cfp":
            assert event.date_from > now().date()
            assert Review.objects.filter(submission__event=event).count() == 0
            assert submissions.filter(state="confirmed").count() == 0
        elif stage == "review":
            assert event.date_from > now().date()
            assert Review.objects.filter(submission__event=event).count() > 0
            assert submissions.filter(state="confirmed").exists()
            assert submissions.filter(state="rejected").exists()
            assert event.schedules.count() == 1  # only wip, no frozen
        elif stage == "schedule":
            assert Review.objects.filter(submission__event=event).count() > 0
            assert submissions.filter(state="confirmed").exists()
            assert event.schedules.filter(version="v1.0").exists()
        else:  # "over"
            assert event.date_from < now().date()
            assert Review.objects.filter(submission__event=event).count() > 0
            assert submissions.filter(state="confirmed").exists()
            assert event.schedules.filter(version="v1.0").exists()


@pytest.mark.django_db
def test_create_test_event_handle_without_admin_returns_early():
    """Calling the command with no admin user exits without creating an event."""
    call_command("create_test_event", slug="no-admin", seed="42")

    with scopes_disabled():
        assert not Event.objects.filter(slug="no-admin").exists()


@pytest.mark.django_db
def test_create_test_event_handle_without_seed():
    """Calling the command without a seed still works (Faker.seed not called)."""
    UserFactory(is_administrator=True)

    call_command("create_test_event", stage="cfp", slug="no-seed")

    with scopes_disabled():
        assert Event.objects.filter(slug="no-seed").exists()


@pytest.mark.django_db
def test_build_speaker_reuses_existing_user(event):
    """When a user with the generated email already exists, build_speaker reuses them."""
    cmd = Command(stdout=StringIO(), stderr=StringIO())
    Faker.seed(99)
    cmd.fake = Faker()
    cmd.event = event

    # Peek at the email build_speaker will generate, then reset
    next_email = cmd.fake.user_name() + "@example.org"
    Faker.seed(99)
    cmd.fake = Faker()
    User.objects.create_user(name="Pre-existing", email=next_email)

    with scopes_disabled():
        speaker = cmd.build_speaker()

        assert speaker.user.email == next_email
        assert SpeakerProfile.objects.filter(
            user__email=next_email, event=event
        ).exists()
