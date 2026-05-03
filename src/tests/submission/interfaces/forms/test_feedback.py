# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms

from pretalx.submission.interfaces.forms import FeedbackForm
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_feedback_form_init_sets_speaker_queryset_to_talk_speakers():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)
    SpeakerFactory(event=submission.event)

    form = FeedbackForm(talk=submission)

    assert list(form.fields["speaker"].queryset) == [speaker]


def test_feedback_form_init_hides_speaker_field_for_single_speaker():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    form = FeedbackForm(talk=submission)

    assert isinstance(form.fields["speaker"].widget, forms.HiddenInput)


def test_feedback_form_init_shows_speaker_field_for_multiple_speakers():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1, speaker2)

    form = FeedbackForm(talk=submission)

    assert not isinstance(form.fields["speaker"].widget, forms.HiddenInput)
    assert set(form.fields["speaker"].queryset) == {speaker1, speaker2}


def test_feedback_form_speaker_choices_use_display_name():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    form = FeedbackForm(talk=submission)

    assert (
        form.fields["speaker"].label_from_instance(speaker)
        == speaker.get_display_name()
    )


def test_feedback_form_save_delegates_to_talk():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    form = FeedbackForm(talk=submission, data={"review": "Wonderful!", "speaker": ""})
    assert form.is_valid(), form.errors
    feedback = form.save()

    assert feedback.pk is not None
    assert feedback.talk == submission
    assert feedback.review == "Wonderful!"


def test_feedback_form_honeypot_rejects_spam():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    form = FeedbackForm(
        talk=submission,
        data={"review": "Buy my product!", "speaker": "", "subject": "on"},
    )

    assert not form.is_valid()
    assert "subject" in form.errors
