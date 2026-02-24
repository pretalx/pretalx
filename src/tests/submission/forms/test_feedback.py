import pytest
from django import forms
from django_scopes import scopes_disabled

from pretalx.submission.forms.feedback import FeedbackForm
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_feedback_form_init_sets_speaker_queryset_to_talk_speakers():
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker)
        SpeakerFactory(event=submission.event)

        form = FeedbackForm(talk=submission)

    assert list(form.fields["speaker"].queryset) == [speaker]


@pytest.mark.django_db
def test_feedback_form_init_hides_speaker_field_for_single_speaker():
    """When a talk has only one speaker, the speaker field is a hidden input."""
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker)

        form = FeedbackForm(talk=submission)

    assert isinstance(form.fields["speaker"].widget, forms.HiddenInput)


@pytest.mark.django_db
def test_feedback_form_init_shows_speaker_field_for_multiple_speakers():
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker1 = SpeakerFactory(event=submission.event)
        speaker2 = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker1, speaker2)

        form = FeedbackForm(talk=submission)

    assert not isinstance(form.fields["speaker"].widget, forms.HiddenInput)
    assert set(form.fields["speaker"].queryset) == {speaker1, speaker2}


@pytest.mark.django_db
def test_feedback_form_save_auto_assigns_speaker_when_single():
    """When there is only one speaker and none is selected, save() assigns them."""
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker)

        form = FeedbackForm(
            talk=submission, data={"review": "Wonderful!", "speaker": ""}
        )
        assert form.is_valid(), form.errors
        feedback = form.save()

    assert feedback.pk is not None
    assert feedback.speaker == speaker
    assert feedback.talk == submission
    assert feedback.review == "Wonderful!"


@pytest.mark.django_db
def test_feedback_form_save_uses_selected_speaker():
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker1 = SpeakerFactory(event=submission.event)
        speaker2 = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker1, speaker2)

        form = FeedbackForm(
            talk=submission, data={"review": "Nice!", "speaker": speaker2.pk}
        )
        assert form.is_valid(), form.errors
        feedback = form.save()

    assert feedback.speaker == speaker2


@pytest.mark.django_db
def test_feedback_form_save_no_speaker_with_multiple_speakers():
    """When no speaker is selected and there are multiple, speaker stays None."""
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker1 = SpeakerFactory(event=submission.event)
        speaker2 = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker1, speaker2)

        form = FeedbackForm(
            talk=submission, data={"review": "Good session", "speaker": ""}
        )
        assert form.is_valid(), form.errors
        feedback = form.save()

    assert feedback.speaker is None


@pytest.mark.django_db
def test_feedback_form_honeypot_rejects_spam():
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker)

        form = FeedbackForm(
            talk=submission,
            data={"review": "Buy my product!", "speaker": "", "subject": "on"},
        )

    assert not form.is_valid()
    assert "subject" in form.errors
