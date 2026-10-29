# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django_scopes import scope, scopes_disabled

from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.orga.forms.submission import AddSpeakerForm, SubmissionStateChangeForm
from pretalx.person.enums import SpeakerProfileOrigin
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

INVITE_DATA = {
    "invite_subject": "Claim your speaker profile",
    "invite_text": "Please claim your profile: {invitation_link}",
}
INVITE_TEXT_REQUIRED = "Please provide a text for the invitation email."
INVITATION_LINK_REQUIRED = (
    "Without the {invitation_link} placeholder, the speaker has no way to claim "
    "their profile. Please leave it in the text."
)
SPEAKER_EXISTS = "This speaker already exists."


@pytest.mark.parametrize(
    ("data", "pending"), (({"pending": True}, True), ({}, False)), ids=["on", "off"]
)
def test_submission_state_change_form_pending(data, pending):
    form = SubmissionStateChangeForm(data=data)

    assert form.is_valid()
    assert form.cleaned_data["pending"] is pending


def test_add_speaker_form_unbound_defaults(event):
    form = AddSpeakerForm(event=event)

    assert list(form.fields) == [
        "speaker",
        "name",
        "email",
        "confirm_email_less",
        "send_invite",
        "invite_subject",
        "invite_text",
    ]
    assert form.fields["send_invite"].initial is False
    assert form.fields["invite_subject"].initial
    assert "{invitation_link}" in form.fields["invite_text"].initial
    assert "{proposal_title}" in form.fields["invite_text"].initial
    assert form.has_speaker_data is False
    rendered = str(form["speaker"])
    assert f'data-remote-url="{event.orga_urls.speaker_search}"' in rendered
    assert "data-existing-selectable" not in rendered


def test_add_speaker_form_standalone_defaults_and_prefill(event):
    form = AddSpeakerForm(event=event, standalone=True)

    assert form.fields["send_invite"].initial is True
    rendered = str(form["speaker"])
    assert 'data-existing-selectable="false"' in rendered
    assert f'data-existing-note="{SPEAKER_EXISTS}"' in rendered
    text = form.fields["invite_text"].initial
    assert "{proposal_title}" not in text
    assert "{invitation_link}" in text

    bound = AddSpeakerForm(
        event=event,
        standalone=True,
        data={
            "email": "new@example.com",
            "send_invite": "on",
            "invite_subject": str(form.fields["invite_subject"].initial),
            "invite_text": str(text),
        },
    )
    assert bound.is_valid(), bound.errors


def test_add_speaker_form_multilingual_event_renders_invite_per_locale():
    event = EventFactory(locales=["en", "de"], name="Braceless Conf")

    form = AddSpeakerForm(event=event)

    assert [code for code, _ in form.fields["locale"].choices] == ["en", "de"]
    assert form.fields["locale"].initial == event.locale
    variants = form.invite_template_variants
    assert set(variants) == {"en", "de"}
    for variant in variants.values():
        # The link token is the one value that cannot exist before sending.
        assert "{invitation_link}" in variant["text"]
        assert "{event_name}" not in variant["text"]
        assert "Braceless Conf" in variant["text"]
    assert variants["en"]["subject"] != variants["de"]["subject"]


@pytest.mark.parametrize(
    ("prefix", "data", "select_name"),
    (
        pytest.param(None, {"speaker": "speaker@example.com"}, "speaker", id="email"),
        pytest.param(
            "speaker",
            {"speaker-speaker": "speaker@example.com"},
            "speaker-speaker",
            id="prefixed-email",
        ),
    ),
)
def test_add_speaker_form_bound_speaker_rendered_as_selected_option(
    event, prefix, data, select_name
):
    form = AddSpeakerForm(event=event, prefix=prefix, data=data)

    html = str(form["speaker"])
    assert f'<select name="{select_name}"' in html
    assert (
        '<option value="speaker@example.com" selected>speaker@example.com</option>'
        in html
    )


def test_add_speaker_form_empty_is_valid_noop(event):
    submission = SubmissionFactory(event=event)
    form = AddSpeakerForm(event=event, data={})
    standalone = AddSpeakerForm(event=event, standalone=True, data={})

    assert form.is_valid(), form.errors
    assert standalone.is_valid(), standalone.errors
    assert form.has_speaker_data is False
    with scope(event=event):
        assert form.add_speaker_to(submission) is None
        assert standalone.create_speaker() is None
        assert submission.speakers.count() == 0


@pytest.mark.parametrize(
    ("standalone", "managed_email", "data", "errors"),
    (
        (
            False,
            None,
            {"speaker": "profile:MANAGED", "send_invite": "on", **INVITE_DATA},
            {
                "send_invite": [
                    "This speaker has no contact email address, so no invitation can be sent."
                ]
            },
        ),
        (
            False,
            "managed@example.com",
            {"speaker": "profile:MANAGED", "send_invite": "on"},
            {
                "invite_subject": [INVITE_TEXT_REQUIRED],
                "invite_text": [INVITE_TEXT_REQUIRED],
            },
        ),
        (
            False,
            None,
            {"email": "new@example.com", "send_invite": "on"},
            {
                "invite_subject": [INVITE_TEXT_REQUIRED],
                "invite_text": [INVITE_TEXT_REQUIRED],
            },
        ),
        (
            False,
            None,
            {
                "email": "new@example.com",
                "send_invite": "on",
                "invite_subject": "Claim your profile",
                "invite_text": "Just say hi, no link at all.",
            },
            {"invite_text": [INVITATION_LINK_REQUIRED]},
        ),
        (
            False,
            None,
            {
                "email": "new@example.com",
                "send_invite": "on",
                "invite_subject": "Claim your profile",
                "invite_text": "Broken { brace. Claim it: {invitation_link}",
            },
            {
                "invite_text": [
                    "Invalid email template! Please check that you don’t have stray { or } somewhere, and that there are no spaces inside the {} blocks."
                ]
            },
        ),
        (
            False,
            None,
            {
                "email": "new@example.com",
                "send_invite": "on",
                "invite_subject": "Claim your profile",
                "invite_text": "Hi {nonexistent}, claim it: {invitation_link}",
            },
            {"invite_text": ["Unknown placeholder! {nonexistent}"]},
        ),
        (
            True,
            None,
            {
                "email": "new@example.com",
                "send_invite": "on",
                "invite_subject": "Claim your profile",
                "invite_text": "About {proposal_title}: {invitation_link}",
            },
            {"invite_text": ["Unknown placeholder! {proposal_title}"]},
        ),
        (
            False,
            None,
            {"speaker": "not-an-email"},
            {"speaker": ["Enter a valid email address."]},
        ),
        (
            False,
            None,
            {"speaker": "profile:NOSUCH"},
            {"speaker": ["This speaker profile does not exist (anymore)."]},
        ),
        (True, None, {"speaker": "profile:MANAGED"}, {"speaker": [SPEAKER_EXISTS]}),
        (
            False,
            None,
            {"name": "Person"},
            {
                "confirm_email_less": [
                    "You have not provided an email address for this speaker, so they cannot be invited or notified. Please confirm that you want to add them anyway."
                ]
            },
        ),
        (False, None, {"name": "Person", "email": "person@example.com"}, {}),
        (False, None, {"name": "Person", "confirm_email_less": "on"}, {}),
    ),
    ids=[
        "managed-invite-without-email",
        "managed-invite-without-text",
        "invite-without-text",
        "invite-without-link",
        "stray-brace",
        "unknown-placeholder",
        "standalone-proposal-placeholder",
        "search-not-an-email",
        "unknown-profile",
        "standalone-profile-pick",
        "email-less-unconfirmed",
        "with-email",
        "email-less-confirmed",
    ],
)
def test_add_speaker_form_clean(event, standalone, managed_email, data, errors):
    SpeakerFactory(event=event, user=None, email=managed_email, code="MANAGED")
    form = AddSpeakerForm(event=event, standalone=standalone, data=data)

    with scope(event=event):
        assert form.is_valid() == (not errors)
    assert form.errors == errors


def test_add_speaker_form_attach_managed_profile_by_code_sends_no_mail(event):
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(event=event, user=None, email="managed@example.com")
    djmail.outbox = []

    with scope(event=event):
        form = AddSpeakerForm(event=event, data={"speaker": f"profile:{managed.code}"})
        assert form.is_valid(), form.errors
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.pk == managed.pk
        assert form.created_profile is False
        assert list(submission.speakers.all()) == [managed]
        assert speaker.invitation_token is None
        assert len(djmail.outbox) == 0
        assert event.queued_mails.count() == 0


def test_add_speaker_form_attach_managed_profile_with_invite_sends_claim_invite(event):
    submission = SubmissionFactory(event=event)
    managed = SpeakerFactory(event=event, user=None, email="managed@example.com")
    djmail.outbox = []

    with scope(event=event):
        form = AddSpeakerForm(
            event=event,
            data={
                "speaker": f"profile:{managed.code}",
                "send_invite": "on",
                **INVITE_DATA,
            },
        )
        assert form.is_valid(), form.errors
        speaker = form.add_speaker_to(submission, user=UserFactory())

        speaker.refresh_from_db()
        assert speaker.pk == managed.pk
        assert list(submission.speakers.all()) == [managed]
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ["managed@example.com"]
        assert speaker.invitation_token in djmail.outbox[0].body


def test_add_speaker_form_attach_self_managed_profile_drafts_notification(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        existing = SpeakerFactory(event=event)
    djmail.outbox = []

    with scope(event=event):
        form = AddSpeakerForm(
            event=event,
            data={
                "speaker": f"profile:{existing.code}",
                "send_invite": "on",
                **INVITE_DATA,
            },
        )
        assert form.is_valid(), form.errors
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.pk == existing.pk
        assert list(submission.speakers.all()) == [existing]
        assert speaker.invitation_token is None
        assert len(djmail.outbox) == 0
        mail = event.queued_mails.get()
        assert mail.state == QueuedMailStates.DRAFT
        assert list(mail.to_speakers.all()) == [existing]


def test_add_speaker_form_invite_prefill_renders_the_proposal(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, title="A Very Fine Talk")

    form = AddSpeakerForm(event=event, submission=submission)
    text = form.fields["invite_text"].initial

    assert "A Very Fine Talk" in text
    assert "{proposal_title}" not in text
    assert "{invitation_link}" in text


def test_add_speaker_form_invite_prefill_keeps_the_name_placeholder_open(event):
    # No speaker is picked yet, so ``{name}`` stays open: the JS fills it
    # in live, and without JavaScript it renders when the mail goes out.
    with scopes_disabled():
        template = mail_template_by_role(event, MailTemplateRoles.NEW_SPEAKER_INVITE)
        template.text = "Hi {name}, claim {event_name}: {invitation_link}"
        template.save()

    form = AddSpeakerForm(event=event)

    assert form.fields["invite_text"].initial == (
        f"Hi {{name}}, claim {event.name}: {{invitation_link}}"
    )


def test_add_speaker_form_invite_keeps_braces_in_substituted_values(event):
    submission = SubmissionFactory(event=event)
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event,
        submission=submission,
        data={
            "email": "new@example.com",
            "name": "Jane {Doe}",
            "send_invite": "on",
            "invite_subject": "Hi {name}",
            "invite_text": "Hi {name}, claim it: {invitation_link}",
        },
    )

    assert form.is_valid(), form.errors
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert len(djmail.outbox) == 1
        body = djmail.outbox[0].body
        assert "Hi Jane {Doe}" in body
        assert speaker.invitation_token in body
        assert djmail.outbox[0].subject.endswith("Hi Jane {Doe}")


def test_add_speaker_form_typed_email_matching_managed_profile_sends_invite(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        existing = SpeakerFactory(
            event=event,
            user=None,
            email="managed@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event,
        data={"email": "managed@example.com", "send_invite": "on", **INVITE_DATA},
    )

    with scope(event=event):
        assert form.is_valid(), form.errors
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.pk == existing.pk
        assert form.created_profile is False
        speaker.refresh_from_db()
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert speaker.invitation_token in djmail.outbox[0].body


def test_add_speaker_form_toggle_off_stores_email_without_mail(event):
    submission = SubmissionFactory(event=event)
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event, data={"email": "deferred@example.com", "name": "Deferred Person"}
    )

    assert "<option" not in str(form["speaker"])
    assert form.is_valid(), form.errors
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        speaker.refresh_from_db()
        assert speaker.user is None
        assert speaker.email == "deferred@example.com"
        assert speaker.invitation_token is None
        assert len(djmail.outbox) == 0
        assert event.queued_mails.count() == 0


def test_add_speaker_form_email_less_speaker_after_confirmation(event):
    submission = SubmissionFactory(event=event)
    form = AddSpeakerForm(
        event=event, data={"name": "No Mail Person", "confirm_email_less": "on"}
    )

    assert form.is_valid(), form.errors
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.user is None
        assert speaker.email is None
        assert speaker.name == "No Mail Person"
        assert list(submission.speakers.all()) == [speaker]


def test_add_speaker_form_email_in_speaker_field_creates_managed_profile(event):
    submission = SubmissionFactory(event=event)
    target = UserFactory()
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event,
        data={
            "speaker": target.email,
            "email": "other@example.com",
            "name": "New Person",
            "send_invite": "on",
            **INVITE_DATA,
        },
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["email"] == target.email
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.user is None
        assert speaker.email == target.email
        assert speaker.name == "New Person"
        assert form.created_profile is True
        assert list(submission.speakers.all()) == [speaker]
        speaker.refresh_from_db()
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == [target.email]
        assert speaker.invitation_token in djmail.outbox[0].body


def test_add_speaker_form_typed_email_matching_self_managed_profile_drafts_notification(
    event,
):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        existing = SpeakerFactory(
            event=event, email="contact@example.com", origin=SpeakerProfileOrigin.ORGA
        )
    djmail.outbox = []
    form = AddSpeakerForm(event=event, data={"email": "contact@example.com"})

    with scope(event=event):
        assert form.is_valid(), form.errors
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.pk == existing.pk
        assert len(djmail.outbox) == 0
        mail = event.queued_mails.get()
        assert mail.state == QueuedMailStates.DRAFT
        assert list(mail.to_speakers.all()) == [existing]
