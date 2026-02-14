# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.submission.models import Submission
from pretalx.submission.rules import (
    can_be_confirmed,
    can_be_removed,
    can_be_reviewed,
    can_be_withdrawn,
    can_view_all_reviews,
    can_view_reviews,
    has_reviewer_access,
    is_speaker,
)


@pytest.mark.django_db
def test_is_speaker_true(event, slot, speaker):
    with scope(event=event):
        assert is_speaker(speaker, slot.submission)
        assert is_speaker(speaker, slot)


@pytest.mark.django_db
def test_is_speaker_false(event, submission, orga_user):
    with scope(event=event):
        assert not is_speaker(orga_user, submission)


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("submitted", True),
        ("accepted", True),
        ("rejected", False),
        ("confirmed", False),
        ("canceled", False),
        ("withdrawn", False),
    ),
)
def test_can_be_withdrawn(state, expected):
    submission = Submission(state=state)
    assert can_be_withdrawn(None, submission) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("submitted", False),
        ("accepted", True),
        ("rejected", False),
        ("confirmed", False),
        ("canceled", False),
        ("withdrawn", False),
    ),
)
def test_can_be_confirmed(state, expected):
    submission = Submission(state=state)
    assert can_be_confirmed(None, submission) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("submitted", True),
        ("accepted", True),
        ("rejected", True),
        ("confirmed", True),
        ("canceled", True),
        ("withdrawn", True),
        ("draft", False),
    ),
)
def test_can_be_removed(state, expected):
    submission = Submission(state=state)
    assert can_be_removed(None, submission) is expected


def test_reviewer_permission_degrades_gracefully():
    assert not has_reviewer_access(None, None)


@pytest.mark.django_db
def test_without_review_phases(event):
    with scope(event=event):
        event.review_phases.all().update(is_active=False)
        assert can_view_all_reviews(None, event) is False
        assert can_view_reviews(None, event) is False


@pytest.mark.django_db
@pytest.mark.parametrize(("value", "expected"), (("always", True), ("never", False)))
def test_can_view_reviews(event, value, expected):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = value
        phase.save()
        assert can_view_reviews(None, event) is expected


def test_can_be_reviewed_false():
    assert not can_be_reviewed(None, None)


@pytest.mark.django_db
def test_can_be_reviewed_true(submission):
    with scope(event=submission.event):
        assert can_be_reviewed(None, submission)
