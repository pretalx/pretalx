# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.orga.views.cards import SubmissionCards
from pretalx.submission.cards import _text
from pretalx.submission.models import SubmissionStates
from tests.factories import SubmissionFactory
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    (
        ("12345", 3, "12…"),
        ("12345", 5, "12345"),
        ("hello", None, "hello"),
        ("", None, ""),
        (None, None, ""),
    ),
)
def test_text_truncation_and_passthrough(text, max_length, expected):
    assert _text(text, max_length) == expected


def test_text_inserts_hair_space_after_hyphens():
    """Hyphens are followed by a hair space for ReportLab word-wrap."""
    assert _text("foo-bar") == "foo-&hairsp;bar"


@pytest.mark.django_db
def test_submission_cards_get_queryset_filters_states(event):
    """get_queryset only returns accepted, confirmed, and submitted submissions."""
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)

    request = make_request(event)
    view = make_view(SubmissionCards, request)

    result = set(view.get_queryset())

    assert result == {accepted, confirmed, submitted}
