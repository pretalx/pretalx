# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.agenda.recording import BaseRecordingProvider, get_recording
from pretalx.agenda.signals import register_recording_provider
from pretalx.submission.models import SubmissionStates
from tests.factories import SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_get_recording_empty_without_providers(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    assert get_recording(submission) == {}


def test_get_recording_returns_first_usable_response(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    payload = {"iframe": "<iframe src='x'></iframe>", "csp_header": "cdn.example"}

    class Provider(BaseRecordingProvider):
        def get_recording(self, submission):
            return payload

    register_signal_handler(
        register_recording_provider, lambda signal, sender, **kw: Provider(sender)
    )

    assert get_recording(submission) == payload


def test_get_recording_skips_handler_exceptions(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    def boom(signal, sender, **kwargs):
        raise ValueError("nope")

    register_signal_handler(register_recording_provider, boom)

    assert get_recording(submission) == {}


def test_get_recording_skips_provider_with_empty_iframe(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    class EmptyProvider(BaseRecordingProvider):
        def get_recording(self, submission):
            return {"iframe": "", "csp_header": ""}

    class GoodProvider(BaseRecordingProvider):
        def get_recording(self, submission):
            return {"iframe": "<iframe/>", "csp_header": "cdn"}

    register_signal_handler(
        register_recording_provider, lambda signal, sender, **kw: EmptyProvider(sender)
    )
    register_signal_handler(
        register_recording_provider, lambda signal, sender, **kw: GoodProvider(sender)
    )

    result = get_recording(submission)

    assert result == {"iframe": "<iframe/>", "csp_header": "cdn"}


def test_get_recording_skips_responses_without_provider(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    register_signal_handler(
        register_recording_provider, lambda signal, sender, **kw: None
    )

    assert get_recording(submission) == {}
