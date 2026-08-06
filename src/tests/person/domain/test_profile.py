# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core import mail as djmail
from django_scopes import scope, scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.person.domain.profile import (
    apply_speaker_profile_changes,
    create_speaker_profile,
    retract_speaker_invite,
    send_speaker_invite,
)
from pretalx.person.enums import SpeakerProfileOrigin
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

INVITE_KWARGS = {
    "subject": "Claim your speaker profile",
    "text": "Please claim your profile: {invitation_link}",
}


def test_apply_speaker_profile_changes_never_touches_account_email():
    profile = SpeakerFactory(
        user=UserFactory(email="old@example.com"), email="contact@example.com"
    )

    apply_speaker_profile_changes(profile, ["email"])
    profile.user.refresh_from_db()

    assert profile.user.email == "old@example.com"


def test_apply_speaker_profile_changes_managed_profile_is_noop():
    profile = SpeakerFactory(user=None, name="Managed Name")

    apply_speaker_profile_changes(profile, ["name", "email"])

    profile.refresh_from_db()
    assert profile.user is None
    assert profile.email is None


def test_apply_speaker_profile_changes_syncs_name_to_empty_user():
    user = UserFactory(name="")
    profile = SpeakerFactory(user=user, name="Fresh Name")

    apply_speaker_profile_changes(profile, ["name"])
    user.refresh_from_db()

    assert user.name == "Fresh Name"


def test_apply_speaker_profile_changes_does_not_overwrite_existing_user_name():
    user = UserFactory(name="Existing Name")
    profile = SpeakerFactory(user=user, name="Profile Name")

    apply_speaker_profile_changes(profile, ["name"])
    user.refresh_from_db()

    assert user.name == "Existing Name"


def test_apply_speaker_profile_changes_skips_name_not_in_changed_fields():
    user = UserFactory(name="")
    profile = SpeakerFactory(user=user, name="Profile Name")

    apply_speaker_profile_changes(profile, [])
    user.refresh_from_db()

    assert user.name == ""


def test_send_speaker_invite_mints_token_and_sends_directly():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    djmail.outbox = []

    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)

    profile.refresh_from_db()
    assert profile.invitation_token
    assert profile.invitation_sent is not None
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["managed@example.com"]
    assert profile.invitation_token in djmail.outbox[0].body
    with scope(event=profile.event):
        mail = profile.mails.get()
        assert mail.state == QueuedMailStates.SENT


def test_send_speaker_invite_resend_rotates_token():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    djmail.outbox = []

    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile.refresh_from_db()
        old_token = profile.invitation_token
        send_speaker_invite(profile, **INVITE_KWARGS)

    profile.refresh_from_db()
    assert profile.invitation_token != old_token
    assert len(djmail.outbox) == 2
    assert profile.invitation_token in djmail.outbox[1].body


def test_send_speaker_invite_uses_edited_subject_and_text():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    djmail.outbox = []

    with scope(event=profile.event):
        send_speaker_invite(
            profile,
            subject="Custom invite subject",
            text="Please claim your profile: {invitation_link}",
        )

    profile.refresh_from_db()
    assert len(djmail.outbox) == 1
    assert "Custom invite subject" in djmail.outbox[0].subject
    assert profile.invitation_token in djmail.outbox[0].body
    with scope(event=profile.event):
        template = profile.event.mail_templates.get(
            role=MailTemplateRoles.NEW_SPEAKER_INVITE
        )
        assert "Custom invite subject" not in str(template.subject)


@pytest.mark.parametrize(
    "profile_kwargs",
    ({"user": None, "email": None}, {}),
    ids=["without_email", "with_account"],
)
def test_send_speaker_invite_rejects_uninvitable_profiles(profile_kwargs):
    profile = SpeakerFactory(**profile_kwargs)

    with scope(event=profile.event), pytest.raises(SendMailException):
        send_speaker_invite(profile, **INVITE_KWARGS)

    profile.refresh_from_db()
    assert profile.invitation_token is None


@pytest.mark.parametrize(
    ("subject", "text"),
    (("", "Some text"), ("Some subject", "")),
    ids=["empty_subject", "empty_text"],
)
def test_send_speaker_invite_requires_subject_and_text(subject, text):
    profile = SpeakerFactory(user=None, email="managed@example.com")

    with (
        scope(event=profile.event),
        pytest.raises(ValueError, match="subject and text"),
    ):
        send_speaker_invite(profile, subject=subject, text=text)

    profile.refresh_from_db()
    assert profile.invitation_token is None


def test_send_speaker_invite_render_failure_does_not_rotate_token():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    djmail.outbox = []

    with scope(event=profile.event), pytest.raises(SendMailException):
        send_speaker_invite(
            profile, subject="Hello", text="About {proposal_title}: {invitation_link}"
        )

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.invitation_sent is None
    assert len(djmail.outbox) == 0


def test_retract_speaker_invite_clears_token_keeps_sent_time():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile.refresh_from_db()
        sent = profile.invitation_sent

        retract_speaker_invite(profile)

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.invitation_sent == sent


def test_retract_speaker_invite_without_token_is_noop():
    profile = SpeakerFactory(user=None, email="managed@example.com")

    retract_speaker_invite(profile)

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.logged_actions().count() == 0


def test_create_speaker_profile_creates_managed_profile_and_logs():
    event = EventFactory()
    djmail.outbox = []

    with scope(event=event):
        profile = create_speaker_profile(
            event,
            email="newperson@example.com",
            name="New Person",
            locale="de",
            log_user=UserFactory(),
        )

        assert profile.event == event
        assert profile.user is None
        assert profile.email == "newperson@example.com"
        assert profile.locale == "de"
        assert profile.origin == SpeakerProfileOrigin.ORGA
        assert list(profile.submissions.all()) == []
        assert profile.invitation_token is None
        assert len(djmail.outbox) == 0
        assert (
            profile.logged_actions()
            .filter(action_type="pretalx.speaker.create")
            .count()
            == 1
        )


def test_create_speaker_profile_never_links_matching_account():
    event = EventFactory()
    account = UserFactory(email="account@example.com")

    with scope(event=event):
        profile = create_speaker_profile(event, email="account@example.com")

        assert profile.user is None
        assert profile.user != account
        assert profile.email == "account@example.com"


def test_create_speaker_profile_requires_email_or_name():
    event = EventFactory()

    with scope(event=event), pytest.raises(ValueError, match="an email or a name"):
        create_speaker_profile(event)
