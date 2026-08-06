# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django_scopes import scope, scopes_disabled

from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.common.forms.widgets import SpeakerSearchSelect
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.orga.forms.submission import (
    AddSpeakerForm,
    AddSpeakerInlineForm,
    SubmissionStateChangeForm,
)
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

INVITE_DATA = {
    "invite_subject": "Claim your speaker profile",
    "invite_text": "Please claim your profile: {invitation_link}",
}


def test_submission_state_change_form_pending_field():
    form = SubmissionStateChangeForm()

    assert "pending" in form.fields
    assert form.fields["pending"].required is False
    assert form.fields["pending"].initial is False


def test_submission_state_change_form_valid_with_pending_true():
    form = SubmissionStateChangeForm(data={"pending": True})

    assert form.is_valid()
    assert form.cleaned_data["pending"] is True


def test_submission_state_change_form_valid_without_data():
    form = SubmissionStateChangeForm(data={})

    assert form.is_valid()
    assert form.cleaned_data["pending"] is False


def test_add_speaker_form_init_removes_locale_for_single_locale(event):
    form = AddSpeakerForm(event=event)

    assert "locale" not in form.fields


def test_add_speaker_form_init_keeps_locale_for_multiple_locales():
    event = EventFactory(locales=["en", "de"])

    form = AddSpeakerForm(event=event)

    assert "locale" in form.fields
    locale_codes = [code for code, _ in form.fields["locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes
    assert form.fields["locale"].initial == event.locale


def test_add_speaker_form_prefills_invite_text_from_template(event):
    form = AddSpeakerForm(event=event)

    assert form.fields["invite_subject"].initial
    assert "{invitation_link}" in form.fields["invite_text"].initial


def test_add_speaker_form_speaker_uses_speaker_search_select_widget(event):
    form = AddSpeakerForm(event=event)

    assert isinstance(form.fields["speaker"].widget, SpeakerSearchSelect)
    assert "<option" not in str(form["speaker"])


def test_add_speaker_form_widget_carries_search_url(event):
    form = AddSpeakerForm(event=event)

    rendered = str(form["speaker"])
    assert f'data-remote-url="{event.orga_urls.speaker_search}"' in rendered


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


def test_add_speaker_form_bound_without_speaker_renders_no_options(event):
    form = AddSpeakerForm(event=event, data={"email": "speaker@example.com"})

    assert "<option" not in str(form["speaker"])


def test_add_speaker_form_has_speaker_data_false_before_validation(event):
    form = AddSpeakerForm(event=event)

    assert form.has_speaker_data is False


def test_add_speaker_form_create_speaker_without_data_returns_none(event):
    form = AddSpeakerForm(event=event, standalone=True, data={})

    assert form.is_valid(), form.errors
    with scope(event=event):
        assert form.create_speaker() is None


def test_add_speaker_form_empty_is_valid_noop(event):
    submission = SubmissionFactory(event=event)
    form = AddSpeakerForm(event=event, data={})

    assert form.is_valid(), form.errors
    assert form.has_speaker_data is False
    with scope(event=event):
        assert form.add_speaker_to(submission) is None
        assert submission.speakers.count() == 0


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


def test_add_speaker_form_attach_managed_profile_invite_requires_email(event):
    managed = SpeakerFactory(event=event, user=None, email=None)

    with scope(event=event):
        form = AddSpeakerForm(
            event=event,
            data={
                "speaker": f"profile:{managed.code}",
                "send_invite": "on",
                **INVITE_DATA,
            },
        )
        assert not form.is_valid()
    assert "send_invite" in form.errors


def test_add_speaker_form_attach_managed_profile_invite_validates_text(event):
    managed = SpeakerFactory(event=event, user=None, email="managed@example.com")

    with scope(event=event):
        form = AddSpeakerForm(
            event=event,
            data={"speaker": f"profile:{managed.code}", "send_invite": "on"},
        )
        assert not form.is_valid()
    assert "invite_subject" in form.errors
    assert "invite_text" in form.errors


def test_add_speaker_form_attach_self_managed_profile_ignores_send_invite(event):
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

        assert speaker.invitation_token is None
        assert len(djmail.outbox) == 0
        mail = event.queued_mails.get()
        assert mail.state == QueuedMailStates.DRAFT


def test_add_speaker_form_standalone_marks_existing_profiles_unselectable(event):
    default = AddSpeakerForm(event=event)
    standalone = AddSpeakerForm(event=event, standalone=True)

    assert "data-existing-selectable" not in str(default["speaker"])
    rendered = str(standalone["speaker"])
    assert 'data-existing-selectable="false"' in rendered
    assert "data-existing-note" in rendered


def test_add_speaker_form_invite_template_variants_are_rendered_per_locale():
    event = EventFactory(locales=["en", "de"], name="Braceless Conf")

    form = AddSpeakerForm(event=event)
    variants = form.invite_template_variants

    assert set(variants) == {"en", "de"}
    for variant in variants.values():
        # The link token is the one value that cannot exist before sending.
        assert "{invitation_link}" in variant["text"]
        assert "{event_name}" not in variant["text"]
        assert "Braceless Conf" in variant["text"]
    assert variants["en"]["subject"] != variants["de"]["subject"]


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


def test_add_speaker_form_invite_prefill_keeps_proposal_placeholder_without_proposal(
    event,
):
    form = AddSpeakerForm(event=event)

    assert "{proposal_title}" in form.fields["invite_text"].initial


def test_add_speaker_form_standalone_prefill_has_no_proposal_placeholders(event):
    form = AddSpeakerForm(event=event, standalone=True)
    text = form.fields["invite_text"].initial

    assert "{proposal_title}" not in text
    assert "{invitation_link}" in text


def test_add_speaker_form_standalone_accepts_its_own_prefill(event):
    unbound = AddSpeakerForm(event=event, standalone=True)
    form = AddSpeakerForm(
        event=event,
        standalone=True,
        data={
            "email": "new@example.com",
            "send_invite": "on",
            "invite_subject": str(unbound.fields["invite_subject"].initial),
            "invite_text": str(unbound.fields["invite_text"].initial),
        },
    )

    assert form.is_valid(), form.errors


def test_add_speaker_form_standalone_rejects_proposal_placeholders(event):
    form = AddSpeakerForm(
        event=event,
        standalone=True,
        data={
            "email": "new@example.com",
            "send_invite": "on",
            "invite_subject": "Claim your profile",
            "invite_text": "About {proposal_title}: {invitation_link}",
        },
    )

    assert not form.is_valid()
    assert "invite_text" in form.errors
    assert "{proposal_title}" in str(form.errors["invite_text"])


def test_add_speaker_form_invite_requires_the_invitation_link(event):
    form = AddSpeakerForm(
        event=event,
        data={
            "email": "new@example.com",
            "send_invite": "on",
            "invite_subject": "Claim your profile",
            "invite_text": "Just say hi, no link at all.",
        },
    )

    assert not form.is_valid()
    assert "invite_text" in form.errors


@pytest.mark.parametrize(
    ("invite_text", "error"),
    (
        ("Broken { brace. Claim it: {invitation_link}", "stray"),
        ("Hi {nonexistent}, claim it: {invitation_link}", "Unknown placeholder"),
    ),
)
def test_add_speaker_form_invite_validates_text_as_template(event, invite_text, error):
    form = AddSpeakerForm(
        event=event,
        data={
            "email": "new@example.com",
            "send_invite": "on",
            "invite_subject": "Claim your profile",
            "invite_text": invite_text,
        },
    )

    assert not form.is_valid()
    assert error in str(form.errors["invite_text"])


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


def test_add_speaker_form_attach_self_managed_profile_drafts_notification(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        existing = SpeakerFactory(event=event)
    djmail.outbox = []

    with scope(event=event):
        form = AddSpeakerForm(event=event, data={"speaker": f"profile:{existing.code}"})
        assert form.is_valid(), form.errors
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.pk == existing.pk
        assert list(submission.speakers.all()) == [existing]
        assert len(djmail.outbox) == 0
        mail = event.queued_mails.get()
        assert mail.state == QueuedMailStates.DRAFT
        assert list(mail.to_speakers.all()) == [existing]


def test_add_speaker_form_unknown_profile_code_is_rejected(event):
    form = AddSpeakerForm(event=event, data={"speaker": "profile:NOSUCH"})

    with scope(event=event):
        assert not form.is_valid()
    assert "speaker" in form.errors


def test_add_speaker_form_new_email_with_invite_sends_claim_invite(event):
    submission = SubmissionFactory(event=event)
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event,
        data={
            "email": "new@example.com",
            "name": "New Person",
            "send_invite": "on",
            **INVITE_DATA,
        },
    )

    assert form.is_valid(), form.errors
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        speaker.refresh_from_db()
        assert speaker.user is None
        assert speaker.email == "new@example.com"
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ["new@example.com"]
        assert speaker.invitation_token in djmail.outbox[0].body


def test_add_speaker_form_typed_email_matching_managed_profile_sends_invite(event):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        existing = SpeakerFactory(event=event, user=None, email="managed@example.com")
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


def test_add_speaker_form_standalone_rejects_profile_pick(event):
    with scopes_disabled():
        existing = SpeakerFactory(event=event, user=None)
    form = AddSpeakerForm(
        event=event, standalone=True, data={"speaker": f"profile:{existing.code}"}
    )

    with scope(event=event):
        assert not form.is_valid()
    assert "speaker" in form.errors


def test_add_speaker_form_toggle_off_stores_email_without_mail(event):
    submission = SubmissionFactory(event=event)
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event, data={"email": "deferred@example.com", "name": "Deferred Person"}
    )

    assert form.is_valid(), form.errors
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        speaker.refresh_from_db()
        assert speaker.user is None
        assert speaker.email == "deferred@example.com"
        assert speaker.invitation_token is None
        assert len(djmail.outbox) == 0
        assert event.queued_mails.count() == 0


def test_add_speaker_form_email_less_requires_confirmation_round_trip(event):
    submission = SubmissionFactory(event=event)
    form = AddSpeakerForm(event=event, data={"name": "No Mail Person"})

    assert not form.is_valid()
    assert "confirm_email_less" in form.errors

    confirmed = AddSpeakerForm(
        event=event, data={"name": "No Mail Person", "confirm_email_less": "on"}
    )
    assert confirmed.is_valid(), confirmed.errors
    with scope(event=event):
        speaker = confirmed.add_speaker_to(submission, user=UserFactory())

        assert speaker.user is None
        assert speaker.email is None
        assert speaker.name == "No Mail Person"
        assert list(submission.speakers.all()) == [speaker]


def test_add_speaker_form_confirmation_checkbox_only_required_when_needed(event):
    unbound = AddSpeakerForm(event=event)
    with_email = AddSpeakerForm(
        event=event, data={"name": "Person", "email": "person@example.com"}
    )
    email_less = AddSpeakerForm(event=event, data={"name": "Person"})

    assert "confirm_email_less" in unbound.fields
    assert with_email.is_valid(), with_email.errors
    assert not email_less.is_valid()
    assert "confirm_email_less" in email_less.errors


def test_add_speaker_form_free_typed_email_in_search_wins_over_email_field(event):
    form = AddSpeakerForm(
        event=event, data={"speaker": "typed@example.com", "email": "other@example.com"}
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["email"] == "typed@example.com"


def test_add_speaker_form_search_value_must_be_email_or_profile(event):
    form = AddSpeakerForm(event=event, data={"speaker": "not-an-email"})

    assert not form.is_valid()
    assert "speaker" in form.errors


def test_add_speaker_form_email_in_speaker_field_creates_managed_profile(event):
    submission = SubmissionFactory(event=event)
    target = UserFactory()
    djmail.outbox = []
    form = AddSpeakerForm(
        event=event, data={"speaker": target.email, "send_invite": "on", **INVITE_DATA}
    )

    assert form.is_valid(), form.errors
    with scope(event=event):
        speaker = form.add_speaker_to(submission, user=UserFactory())

        assert speaker.user is None
        assert speaker.email == target.email
        assert form.created_profile is True
        assert list(submission.speakers.all()) == [speaker]
        speaker.refresh_from_db()
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert speaker.invitation_token in djmail.outbox[0].body


def test_add_speaker_form_typed_email_matching_self_managed_profile_drafts_notification(
    event,
):
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        existing = SpeakerFactory(event=event, email="contact@example.com")
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


def test_add_speaker_form_invite_requires_subject_and_text(event):
    form = AddSpeakerForm(
        event=event, data={"email": "new@example.com", "send_invite": "on"}
    )

    assert not form.is_valid()
    assert "invite_subject" in form.errors
    assert "invite_text" in form.errors


def test_add_speaker_inline_form_uses_inline_renderer(event):

    form = AddSpeakerInlineForm(event=event)

    assert form.default_renderer is InlineFormLabelRenderer
