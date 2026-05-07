# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils.timezone import now

from pretalx.person.domain.user import create_user
from pretalx.person.models import SpeakerProfile, User
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("input_email", "expected_email"),
    (
        ("Test@Example.COM", "test@example.com"),
        ("  UPPER@EXAMPLE.COM  ", "upper@example.com"),
    ),
    ids=["lowercases", "strips_and_lowercases"],
)
def test_create_user_normalizes_email(input_email, expected_email):
    user = create_user(email=input_email)

    assert isinstance(user, User)
    assert user.email == expected_email


def test_create_user_empty_name_defaults_to_empty_string():
    user = create_user(email="test@example.com")

    assert user.name == ""


def test_create_user_without_password_sets_pw_reset_token():
    user = create_user(email="test@example.com")

    assert user.pw_reset_token
    assert len(user.pw_reset_token) == 32
    assert user.pw_reset_time > now()
    assert not user.has_usable_password() or not user.check_password("")


def test_create_user_with_password_skips_pw_reset_token():
    user = create_user(email="test@example.com", password="hunter2hunter2")

    assert user.pw_reset_token is None
    assert user.pw_reset_time is None
    assert user.check_password("hunter2hunter2")


def test_create_user_passes_locale_and_timezone():
    user = create_user(
        email="test@example.com",
        password="hunter2hunter2",
        locale="de",
        timezone="Europe/Berlin",
    )

    assert user.locale == "de"
    assert user.timezone == "Europe/Berlin"


def test_create_user_creates_speaker_profile_when_event_given():
    event = EventFactory()

    user = create_user(email="test@example.com", event=event)
    assert SpeakerProfile.objects.filter(user=user, event=event).exists()


def test_create_user_no_speaker_profile_without_event():
    user = create_user(email="test@example.com")

    assert not SpeakerProfile.objects.filter(user=user).exists()
