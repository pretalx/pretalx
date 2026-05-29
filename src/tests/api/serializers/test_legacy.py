# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.serializers.legacy import LegacySubmissionSerializer
from tests.factories import EventFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_legacy_get_attribute_returns_original_for_privileged_viewer():
    submission = SubmissionFactory(
        event=EventFactory(),
        abstract="Original abstract",
        anonymised={"_anonymised": True, "abstract": "Redacted abstract"},
    )
    serializer = LegacySubmissionSerializer(submission, can_view_speakers=True)

    assert serializer.get_attribute(submission, attribute="abstract") == (
        "Original abstract"
    )


def test_legacy_get_attribute_returns_redacted_for_anonymised_viewer():
    submission = SubmissionFactory(
        event=EventFactory(),
        abstract="Original abstract",
        anonymised={"_anonymised": True, "abstract": "Redacted abstract"},
    )
    serializer = LegacySubmissionSerializer(submission, can_view_speakers=False)

    assert serializer.get_attribute(submission, attribute="abstract") == (
        "Redacted abstract"
    )


def test_legacy_get_attribute_respects_blanked_redaction():
    submission = SubmissionFactory(
        event=EventFactory(),
        abstract="Hi, I am Jane Doe from BigCorp.",
        anonymised={"_anonymised": True, "abstract": ""},
    )
    serializer = LegacySubmissionSerializer(submission, can_view_speakers=False)

    assert serializer.get_attribute(submission, attribute="abstract") == ""
