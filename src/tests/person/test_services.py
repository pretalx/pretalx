import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.person.models import SpeakerProfile, User
from pretalx.person.services import create_user
from tests.factories import EventFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("input_email", "expected_email"),
    (
        ("Test@Example.COM", "test@example.com"),
        ("  UPPER@EXAMPLE.COM  ", "upper@example.com"),
    ),
    ids=["lowercases", "strips_and_lowercases"],
)
def test_create_user_normalizes_email(input_email, expected_email):
    user = create_user(input_email)

    assert isinstance(user, User)
    assert user.email == expected_email


@pytest.mark.django_db
def test_create_user_empty_name_defaults_to_empty_string():
    user = create_user("test@example.com")

    assert user.name == ""


@pytest.mark.django_db
def test_create_user_sets_pw_reset_token():
    user = create_user("test@example.com")

    assert user.pw_reset_token
    assert len(user.pw_reset_token) == 32
    assert user.pw_reset_time > now()


@pytest.mark.django_db
def test_create_user_creates_speaker_profile_when_event_given():
    event = EventFactory()

    with scopes_disabled():
        user = create_user("test@example.com", event=event)
        assert SpeakerProfile.objects.filter(user=user, event=event).exists()


@pytest.mark.django_db
def test_create_user_no_speaker_profile_without_event():
    user = create_user("test@example.com")

    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(user=user).exists()
