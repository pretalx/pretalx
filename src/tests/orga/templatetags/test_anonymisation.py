# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.orga.templatetags.anonymisation import anonymised_value
from pretalx.submission.models import Submission

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("anonymised", "expected"),
    (
        (None, "Original"),
        ({"_anonymised": True, "title": "Redacted"}, "Redacted"),
        ({"_anonymised": True, "title": ""}, ""),
    ),
    ids=["not_anonymised", "redacted", "blanked"],
)
def test_anonymised_value(anonymised, expected):
    submission = Submission(title="Original")
    submission.anonymised = anonymised
    assert anonymised_value(submission, "title") == expected
