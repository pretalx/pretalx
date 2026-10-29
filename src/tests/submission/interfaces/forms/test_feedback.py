# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms

from pretalx.submission.interfaces.forms import FeedbackForm
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_feedback_form_speaker_field_follows_talk_speakers():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)
    SpeakerFactory(event=submission.event)

    form = FeedbackForm(talk=submission)

    assert list(form.fields["speaker"].queryset) == [speaker]
    assert isinstance(form.fields["speaker"].widget, forms.HiddenInput)
    assert (
        form.fields["speaker"].label_from_instance(speaker)
        == speaker.get_display_name()
    )

    form = FeedbackForm(
        talk=submission,
        data={"review": "Buy my product!", "speaker": "", "subject": "on"},
    )

    assert not form.is_valid()
    assert "subject" in form.errors

    form = FeedbackForm(talk=submission, data={"review": "Wonderful!", "speaker": ""})
    assert form.is_valid(), form.errors
    feedback = form.save()

    assert feedback.talk == submission
    assert feedback.review == "Wonderful!"
    assert feedback.speaker == speaker

    other = SpeakerFactory(event=submission.event)
    submission.speakers.add(other)

    form = FeedbackForm(talk=submission)

    assert not isinstance(form.fields["speaker"].widget, forms.HiddenInput)
    assert set(form.fields["speaker"].queryset) == {speaker, other}
