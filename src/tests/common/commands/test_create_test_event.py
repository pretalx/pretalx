# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils.timezone import now
from faker import Faker

from pretalx.common.management.commands.create_test_event import Command, schedule_slot
from pretalx.event.models import Event
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Review
from tests.factories.person import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_schedule_slot_sets_start_end_room(talk_slot):
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
    assert talk_slot.room_id == room.pk


@pytest.mark.parametrize(
    ("existing", "expected_email"),
    (((), "fresh@example.org"), (("fresh@example.org",), "fresh1@example.org")),
    ids=("free", "retries_on_duplicate"),
)
def test_create_user_with_retry(existing, expected_email):
    for email in existing:
        UserFactory(name="Existing", email=email)
    cmd = Command(stdout=StringIO(), stderr=StringIO())

    user = cmd.create_user_with_retry(name="New User", email_base="fresh@example.org")

    assert user.name == "New User"
    assert user.email == expected_email


def test_create_user_with_retry_exhausts_retries_raises():
    cmd = Command(stdout=StringIO(), stderr=StringIO())
    for i in range(3):
        email = "clash@example.org" if i == 0 else f"clash{i}@example.org"
        UserFactory(name=f"Blocker {i}", email=email)

    with pytest.raises(ValidationError):
        cmd.create_user_with_retry(
            name="Unlucky", email_base="clash@example.org", max_retries=3
        )


def test_build_event_without_admin_returns_none():
    cmd = Command(stdout=StringIO(), stderr=StringIO())

    result = cmd.build_event("schedule", "test-slug")

    assert result is None


@pytest.mark.slow
@pytest.mark.parametrize(
    ("stage", "seed"),
    (("cfp", None), ("review", "42"), ("schedule", "42"), ("over", "42")),
    ids=("cfp-unseeded", "review", "schedule", "over"),
)
def test_create_test_event_end_to_end(stage, seed):
    UserFactory(is_administrator=True)
    slug = f"demo-{stage}"

    call_command("create_test_event", stage=stage, slug=slug, seed=seed)

    event = Event.objects.get(slug=slug)
    assert event.name == "DemoCon"
    assert event.rooms.count() == 2
    assert event.tracks.count() >= 2
    assert event.cfp is not None
    submissions = event.submissions.all()
    assert submissions.count() > 0

    match stage:
        case "cfp":
            assert event.date_from > now().date()
            assert Review.objects.filter(submission__event=event).count() == 0
            assert submissions.filter(state="confirmed").count() == 0
        case "review":
            assert event.date_from > now().date()
            assert Review.objects.filter(submission__event=event).count() > 0
            assert submissions.filter(state="confirmed").exists()
            assert submissions.filter(state="rejected").exists()
            assert event.schedules.count() == 1  # only wip, no frozen
        case "schedule":
            assert Review.objects.filter(submission__event=event).count() > 0
            assert submissions.filter(state="confirmed").exists()
            assert event.schedules.filter(version="v1.0").exists()
        case _:  # "over"
            assert event.date_from < now().date()
            assert Review.objects.filter(submission__event=event).count() > 0
            assert submissions.filter(state="confirmed").exists()
            assert event.schedules.filter(version="v1.0").exists()


def test_create_test_event_handle_without_admin_returns_early():
    call_command("create_test_event", slug="no-admin", seed="42")

    assert not Event.objects.filter(slug="no-admin").exists()


def test_build_speaker_reuses_existing_user_and_profile(event):
    cmd = Command(stdout=StringIO(), stderr=StringIO())
    Faker.seed(99)
    cmd.fake = Faker()
    cmd.event = event

    # Peek at the email build_speaker will generate, then reset
    next_email = cmd.fake.user_name() + "@example.org"
    Faker.seed(99)
    cmd.fake = Faker()
    user = UserFactory(name="Pre-existing", email=next_email)
    profile = SpeakerProfile.objects.create(user=user, event=event)

    speaker = cmd.build_speaker()

    assert speaker == profile
    assert speaker.user.email == next_email
