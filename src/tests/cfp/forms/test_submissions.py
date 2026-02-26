import pytest
from django.core import mail as djmail
from django_scopes import scopes_disabled

from pretalx.cfp.forms.submissions import SubmissionInvitationForm
from pretalx.submission.models import SubmissionInvitation

pytestmark = pytest.mark.unit


def _make_form(submission, speaker_user, data=None, **kwargs):
    """Helper to build a SubmissionInvitationForm with defaults."""
    return SubmissionInvitationForm(
        submission=submission, speaker=speaker_user, data=data, **kwargs
    )


@pytest.mark.django_db
def test_invitation_form_init_populates_subject_and_text(submission_with_speaker):
    submission, speaker_user = submission_with_speaker

    form = _make_form(submission, speaker_user)

    assert speaker_user.get_display_name() in form.initial["subject"]
    assert str(submission.event.name) in form.initial["text"]
    assert str(submission.title) in form.initial["text"]
    assert "{invitation_url}" in form.initial["text"]


@pytest.mark.django_db
def test_invitation_form_valid_with_correct_data(submission_with_speaker):
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "new-speaker@example.com",
                "subject": "You're invited!",
                "text": "Join us at {invitation_url} please!",
            },
        )
        assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    "text", ("Join us please!", ""), ids=("missing_placeholder", "empty")
)
@pytest.mark.django_db
def test_invitation_form_clean_text_rejects_invalid_text(submission_with_speaker, text):
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "new-speaker@example.com",
                "subject": "Invite",
                "text": text,
            },
        )
        assert not form.is_valid()
    assert "text" in form.errors


@pytest.mark.parametrize("upcase", (False, True), ids=("exact", "case_insensitive"))
@pytest.mark.django_db
def test_invitation_form_clean_speaker_rejects_existing_speaker(
    submission_with_speaker, upcase
):
    submission, speaker_user = submission_with_speaker
    email = speaker_user.email.upper() if upcase else speaker_user.email

    with scopes_disabled():
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": email,
                "subject": "Invite",
                "text": "Join at {invitation_url}",
            },
        )
        assert not form.is_valid()
    assert "speaker" in form.errors


@pytest.mark.parametrize("upcase", (False, True), ids=("exact", "case_insensitive"))
@pytest.mark.django_db
def test_invitation_form_clean_speaker_rejects_already_invited(
    submission_with_speaker, upcase
):
    submission, speaker_user = submission_with_speaker
    with scopes_disabled():
        SubmissionInvitation.objects.create(
            submission=submission, email="invited@example.com"
        )
        email = "INVITED@example.com" if upcase else "invited@example.com"
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": email,
                "subject": "Invite",
                "text": "Join at {invitation_url}",
            },
        )
        assert not form.is_valid()
    assert "speaker" in form.errors


@pytest.mark.django_db
def test_invitation_form_clean_speaker_lowercases_and_strips(submission_with_speaker):
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "  NewSpeaker@Example.COM  ",
                "subject": "Invite",
                "text": "Join at {invitation_url}",
            },
        )
        assert form.is_valid(), form.errors
    assert form.cleaned_data["speaker"] == "newspeaker@example.com"


@pytest.mark.django_db
def test_invitation_form_clean_speaker_rejects_exceeding_max_speakers(
    submission_with_speaker,
):
    """When max_speakers is set and would be exceeded, validation fails."""
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        cfp = submission.event.cfp
        cfp.fields["additional_speaker"] = {"visibility": "required", "max": 1}
        cfp.save()

        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "extra@example.com",
                "subject": "Invite",
                "text": "Join at {invitation_url}",
            },
        )
        assert not form.is_valid()
    assert "speaker" in form.errors


@pytest.mark.django_db
def test_invitation_form_clean_speaker_allows_within_max_speakers(
    submission_with_speaker,
):
    """When max_speakers is set but not exceeded, validation passes."""
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        cfp = submission.event.cfp
        cfp.fields["additional_speaker"] = {"visibility": "required", "max": 3}
        cfp.save()

        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "extra@example.com",
                "subject": "Invite",
                "text": "Join at {invitation_url}",
            },
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_invitation_form_clean_speaker_counts_pending_invitations_toward_max(
    submission_with_speaker,
):
    """Pending invitations count toward max_speakers limit."""
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        cfp = submission.event.cfp
        cfp.fields["additional_speaker"] = {"visibility": "required", "max": 2}
        cfp.save()
        SubmissionInvitation.objects.create(
            submission=submission, email="pending@example.com"
        )

        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "extra@example.com",
                "subject": "Invite",
                "text": "Join at {invitation_url}",
            },
        )
        assert not form.is_valid()
    assert "speaker" in form.errors


@pytest.mark.django_db
def test_invitation_form_save_creates_invitation_and_sends_email(
    submission_with_speaker,
):
    djmail.outbox = []
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "new-speaker@example.com",
                "subject": "You're invited!",
                "text": "Join us at {invitation_url} please!",
            },
        )
        assert form.is_valid(), form.errors
        invitation = form.save()

    assert invitation.pk is not None
    assert invitation.submission == submission
    assert invitation.email == "new-speaker@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["new-speaker@example.com"]
    assert "You're invited!" in djmail.outbox[0].subject


@pytest.mark.django_db
def test_invitation_form_save_replaces_placeholder_in_text(submission_with_speaker):
    djmail.outbox = []
    submission, speaker_user = submission_with_speaker

    with scopes_disabled():
        form = _make_form(
            submission,
            speaker_user,
            data={
                "speaker": "new-speaker@example.com",
                "subject": "Invite",
                "text": "Click here: {invitation_url} to join.",
            },
        )
        assert form.is_valid(), form.errors
        invitation = form.save()

    assert len(djmail.outbox) == 1
    body = djmail.outbox[0].body
    assert "{invitation_url}" not in body
    assert invitation.token in body


@pytest.mark.django_db
def test_invitation_form_save_returns_existing_without_resending(
    submission_with_speaker,
):
    """If an invitation already exists for this email+submission, return it without sending."""
    djmail.outbox = []
    submission, speaker_user = submission_with_speaker
    with scopes_disabled():
        existing = SubmissionInvitation.objects.create(
            submission=submission, email="repeat@example.com"
        )

    form = _make_form(
        submission,
        speaker_user,
        data={
            "speaker": "repeat@example.com",
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    form.cleaned_data = {
        "speaker": "repeat@example.com",
        "subject": "Invite",
        "text": "Join at {invitation_url}",
    }

    with scopes_disabled():
        result = form.save()

    assert result == existing
    assert len(djmail.outbox) == 0
