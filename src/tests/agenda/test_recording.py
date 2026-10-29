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


def _raise(signal, sender, **kwargs):
    raise ValueError("nope")


def _return_none(signal, sender, **kwargs):
    return None


@pytest.mark.parametrize(
    "handler", (_raise, _return_none), ids=["raising_handler", "no_provider"]
)
def test_get_recording_skips_unusable_handlers(register_signal_handler, event, handler):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    register_signal_handler(register_recording_provider, handler)

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
