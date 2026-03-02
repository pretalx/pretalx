# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.feedback import FeedbackTable
from tests.factories import EventFactory, FeedbackFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def event():
    return EventFactory()


def test_feedback_table_excludes_talk_column_when_not_included(event):
    feedback = FeedbackFactory(talk__event=event)
    table = FeedbackTable(
        [feedback], event=event, user=UserFactory.build(), include_talk=False
    )

    assert "talk" in table.exclude


def test_feedback_table_includes_talk_column_by_default(event):
    feedback = FeedbackFactory(talk__event=event)
    table = FeedbackTable([feedback], event=event, user=UserFactory.build())

    assert "talk" not in table.exclude


def test_feedback_table_empty_text_without_talk(event):
    table = FeedbackTable([], event=event, user=UserFactory.build(), include_talk=False)

    assert "this session" in str(table.empty_text).lower()


def test_feedback_table_empty_text_with_talk(event):
    table = FeedbackTable([], event=event, user=UserFactory.build(), include_talk=True)

    assert "this event" in str(table.empty_text).lower()


def test_feedback_table_render_review_with_markdown(event):
    feedback = FeedbackFactory(talk__event=event, review="**bold text**")
    table = FeedbackTable([feedback], event=event, user=UserFactory.build())

    result = table.render_review(feedback)

    assert "<strong>bold text</strong>" in result


def test_feedback_table_render_review_empty(event):
    feedback = FeedbackFactory(talk__event=event, review="")
    table = FeedbackTable([feedback], event=event, user=UserFactory.build())

    result = table.render_review(feedback)

    assert result == ""


def test_feedback_table_default_columns():
    assert FeedbackTable.default_columns == ("talk", "review", "speaker")
