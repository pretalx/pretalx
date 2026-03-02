# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.agenda.recording import BaseRecordingProvider

pytestmark = pytest.mark.unit


def test_base_recording_provider_init_stores_event():
    event = object()

    provider = BaseRecordingProvider(event)

    assert provider.event is event


def test_base_recording_provider_get_recording_raises_not_implemented():
    provider = BaseRecordingProvider(object())

    with pytest.raises(NotImplementedError):
        provider.get_recording(submission=None)
