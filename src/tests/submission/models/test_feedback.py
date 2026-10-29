# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import FeedbackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_feedback_str_and_event():
    feedback = FeedbackFactory(rating=4)

    assert (
        str(feedback)
        == f"Feedback(event={feedback.talk.event.slug}, talk={feedback.talk.title}, rating=4)"
    )
    assert feedback.event == feedback.talk.event
