# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re

import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretalx.common.domain.queries.log import actions_by
from pretalx.common.exceptions import UserDeletionError
from pretalx.common.models import ActivityLog
from pretalx.common.urls import build_absolute_uri
from pretalx.person.domain.user import (
    change_email,
    change_password,
    create_user,
    deactivate_user,
    get_password_reset_url,
    reset_password,
    shred_user,
)
from pretalx.person.models import ProfilePicture, SpeakerProfile, User
from pretalx.person.signals import delete_user as delete_user_signal
from pretalx.submission.models import Answer
from tests.factories import (
    AnswerFactory,
    EventFactory,
    ProfilePictureFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)

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
    # We mint a random password rather than calling
    # ``set_unusable_password``, so the standard ``has_usable_password``
    # gates (login forms, ``LoginRequiredMixin``) treat the row as a
    # real account waiting on the reset token.
    assert user.has_usable_password()


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


def test_deactivate_user_clears_personal_data():
    user = UserFactory(name="Real Name", email="real@example.com")

    deactivate_user(user)
    user.refresh_from_db()

    assert user.name == "Deleted User"
    assert user.is_active is False
    assert user.is_superuser is False
    assert user.is_administrator is False
    assert user.locale == "en"
    assert user.timezone == "UTC"
    assert not user.has_usable_password()
    assert user.pw_reset_token is None
    assert user.pw_reset_time is None
    assert "deleted_user_" in user.email


def test_deactivate_user_clears_biography():
    speaker = SpeakerFactory(biography="My bio")

    deactivate_user(speaker.user)
    speaker.refresh_from_db()

    assert speaker.biography == ""


def test_deactivate_user_with_profile_picture_clears_fk():
    """Deactivating a user whose profile_picture points to one of their pictures
    must not leave a dangling FK or an active profile picture."""
    user = UserFactory()
    picture = ProfilePictureFactory(user=user)
    user.profile_picture = picture
    user.save()
    picture_pk = picture.pk

    deactivate_user(user)

    user.refresh_from_db()
    assert user.profile_picture_id is None
    assert not ProfilePicture.objects.filter(pk=picture_pk).exists()


def test_deactivate_user_deletes_personal_answers():
    speaker = SpeakerFactory()
    submission = SubmissionFactory(event=speaker.event)
    submission.speakers.add(speaker)

    personal_q = QuestionFactory(
        event=speaker.event, target="submission", contains_personal_data=True
    )
    impersonal_q = QuestionFactory(
        event=speaker.event, target="submission", contains_personal_data=False
    )
    AnswerFactory(question=personal_q, submission=submission, speaker=None)
    impersonal = AnswerFactory(
        question=impersonal_q, submission=submission, speaker=None
    )

    deactivate_user(speaker.user)

    remaining = list(Answer.objects.all())
    assert remaining == [impersonal]


def test_deactivate_user_retries_on_email_collision(monkeypatch):
    """The scrambled ``deleted_user_*`` email is regenerated until it
    no longer collides — necessary because the random suffix is short
    enough to clash on busy installations."""
    existing = UserFactory(email="deleted_user_AAAAAAAAAAAA@localhost")
    user = UserFactory()
    suffixes = iter(("AAAAAAAAAAAA", "BBBBBBBBBBBB"))
    monkeypatch.setattr(
        "pretalx.person.domain.user.get_random_string", lambda _length: next(suffixes)
    )

    deactivate_user(user)
    user.refresh_from_db()

    assert user.email == "deleted_user_BBBBBBBBBBBB@localhost"
    assert user.email != existing.email


def test_deactivate_user_removes_from_teams():
    user = UserFactory()
    team = TeamFactory()
    team.members.add(user)
    assert team.members.count() == 1

    deactivate_user(user)

    assert team.members.count() == 0


def test_deactivate_user_sends_signal():
    user = UserFactory()
    received = []

    def handler(sender, **kwargs):
        received.append(kwargs["user"])

    delete_user_signal.connect(handler)
    try:
        deactivate_user(user)
    finally:
        delete_user_signal.disconnect(handler)

    assert received == [user]


def test_shred_user_deletes_user():
    user = UserFactory()
    pk = user.pk
    shred_user(user)
    assert not User.objects.filter(pk=pk).exists()


def test_shred_user_raises_with_submissions():
    speaker = SpeakerFactory()
    submission = SubmissionFactory(event=speaker.event)
    submission.speakers.add(speaker)

    with pytest.raises(UserDeletionError):
        shred_user(speaker.user)


def test_shred_user_raises_with_teams():
    user = UserFactory()
    team = TeamFactory()
    team.members.add(user)

    with pytest.raises(UserDeletionError):
        shred_user(user)


def test_shred_user_raises_with_answers():
    """Users with answers (as speaker or submission speaker) cannot be shredded."""
    speaker = SpeakerFactory()
    question = QuestionFactory(event=speaker.event, target="speaker")
    AnswerFactory(question=question, speaker=speaker, submission=None)

    with pytest.raises(UserDeletionError):
        shred_user(speaker.user)


def test_shred_user_sends_signal():
    user = UserFactory()
    received = []

    def handler(sender, **kwargs):
        received.append(kwargs["user"])

    delete_user_signal.connect(handler)
    try:
        shred_user(user)
    finally:
        delete_user_signal.disconnect(handler)

    assert received == [user]


def test_shred_user_cleans_own_actions():
    """Shredding nullifies person references in the shredded user's own actions."""
    user = UserFactory()
    other_user = UserFactory()
    other_user.log_action("pretalx.user.test", person=user)

    action_pk = ActivityLog.objects.filter(person=user).first().pk

    shred_user(user)

    action = ActivityLog.objects.get(pk=action_pk)
    assert action.person is None


def test_shred_user_deletes_logged_actions():
    user = UserFactory()
    user.log_action("pretalx.user.test")

    assert user.logged_actions().count() == 1

    shred_user(user)

    assert not ActivityLog.objects.filter(object_id=user.pk).exists()


@pytest.mark.parametrize(
    ("use_event", "orga", "expected_urlname"),
    (
        (True, False, "cfp:event.recover"),
        (True, True, "orga:event.auth.recover"),
        (False, False, "orga:auth.recover"),
    ),
    ids=["cfp_with_event", "orga_with_event", "without_event"],
)
def test_get_password_reset_url(use_event, orga, expected_urlname, event):
    user = UserFactory(pw_reset_token="abc123")

    kwargs = {"event": event, "orga": orga} if use_event else {"event": None}
    url = get_password_reset_url(user, **kwargs)

    expected_kwargs = {"token": "abc123"}
    if use_event:
        expected_kwargs["event"] = event.slug
    assert url == build_absolute_uri(expected_urlname, kwargs=expected_kwargs)


def test_reset_password(event):
    user = UserFactory()
    assert user.pw_reset_token is None
    djmail.outbox = []

    reset_password(user, event=event)
    user.refresh_from_db()

    assert len(user.pw_reset_token) == 32
    assert user.pw_reset_time is not None
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    actions = list(actions_by(user).filter(action_type="pretalx.user.password.reset"))
    assert len(actions) == 1


def test_reset_password_custom_text(event):
    user = UserFactory()
    djmail.outbox = []

    reset_password(user, event=event, mail_text="Custom {name} {url}")

    assert len(djmail.outbox) == 1
    expected_url = get_password_reset_url(user, event=event)
    assert djmail.outbox[0].body == f"Custom {user.name} {expected_url}"


def test_change_password():
    user = UserFactory()
    djmail.outbox = []

    change_password(user, "newpassword123!")

    user.refresh_from_db()
    assert user.check_password("newpassword123!")
    assert user.pw_reset_token is None
    assert user.pw_reset_time is None
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    actions = list(actions_by(user).filter(action_type="pretalx.user.password.update"))
    assert len(actions) == 1


def test_change_email():
    user = UserFactory(email="old@example.com")
    djmail.outbox = []

    change_email(user, "NEW@Example.COM")

    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["old@example.com"]
    action = actions_by(user).filter(action_type="pretalx.user.email.update").first()
    assert action.data == {
        "old_email": "old@example.com",
        "new_email": "new@example.com",
    }


MALICIOUS_NAMES = (
    pytest.param(
        "user,<br>We have detected suspicious activity. "
        '<a href="https://phish.com">Click here to secure your account.</a a=">',
        id="html_cve",
    ),
    pytest.param(
        "[Click here to secure your account](https://phish.com)", id="md_link"
    ),
)


def _assert_safe_mail(sent):
    assert len(sent.alternatives) == 1
    html_body = sent.alternatives[0][0]
    assert '<a href="https://phish.com"' not in html_body
    assert "<br>" not in sent.body
    assert '<a href="https://phish.com"' not in sent.body
    # Plain body must have no unescaped markdown link syntax, or the
    # edited-draft fallback would re-parse it as a live link.
    assert not re.search(r"(?<!\\)\[.*\]\(https://phish", sent.body)


@pytest.mark.parametrize("payload", MALICIOUS_NAMES)
def test_reset_password_neutralises_injection(event, payload):
    user = UserFactory(name=payload)
    djmail.outbox = []

    reset_password(user, event=event)

    assert len(djmail.outbox) == 1
    _assert_safe_mail(djmail.outbox[0])


@pytest.mark.parametrize("payload", MALICIOUS_NAMES)
def test_change_password_neutralises_injection(payload):
    user = UserFactory(name=payload)
    djmail.outbox = []

    change_password(user, "newpassword123!")

    assert len(djmail.outbox) == 1
    _assert_safe_mail(djmail.outbox[0])


@pytest.mark.parametrize("payload", MALICIOUS_NAMES)
def test_change_email_neutralises_injection(payload):
    user = UserFactory(name=payload, email="old@example.com")
    djmail.outbox = []

    change_email(user, "new@example.com")

    assert len(djmail.outbox) == 1
    _assert_safe_mail(djmail.outbox[0])


def test_change_email_neutralises_injection_in_email_address():
    # Django's EmailField accepts RFC 5321 quoted local parts, so a
    # payload like ``"<script>"@example.com`` reaches change_email()
    # and must route through untrusted_plain_value rather than mark_safe.
    email_field = User._meta.get_field("email").formfield()
    malicious = '"<script>alert(1)</script>"@example.com'
    email_field.clean(malicious)  # sanity check

    user = UserFactory(email="old@example.com")
    djmail.outbox = []
    change_email(user, malicious)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    html_body = sent.alternatives[0][0]
    assert "<script>" not in html_body
    assert "alert(1)" in html_body  # as escaped text only
    assert "&lt;script&gt;" in html_body
    assert "<script>" not in sent.body
