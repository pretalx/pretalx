# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.orga.tables.feedback import FeedbackTable
from pretalx.submission.models import Feedback
from tests.factories import EventFactory, FeedbackFactory, SpeakerFactory, UserFactory

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


def test_feedback_table_render_speaker_managed(event):
    speaker = SpeakerFactory(event=event, user=None, name="Managed Speaker")
    feedback = FeedbackFactory(talk__event=event, speaker=speaker)
    table = FeedbackTable([feedback], event=event, user=UserFactory.build())

    assert table.render_speaker(speaker) == "Managed Speaker"


def test_feedback_table_render_speaker_with_user(event):
    speaker = SpeakerFactory(event=event, user__name="User Speaker")
    feedback = FeedbackFactory(talk__event=event, speaker=speaker)
    table = FeedbackTable([feedback], event=event, user=UserFactory.build())

    assert table.render_speaker(speaker) == "User Speaker"


def test_feedback_table_speaker_ordering_uses_display_name(event):
    managed = SpeakerFactory(event=event, user=None, name="Anna")
    account = SpeakerFactory(event=event, user__name="Mia")
    override = SpeakerFactory(event=event, user__name="Bea", name="Zoe")
    feedbacks = {
        speaker: FeedbackFactory(talk__event=event, speaker=speaker)
        for speaker in (managed, account, override)
    }

    column = FeedbackTable.base_columns["speaker"]
    with scopes_disabled():
        ordered, modified = column.order(
            Feedback.objects.filter(talk__event=event), is_descending=False
        )

        assert modified is True
        assert list(ordered) == [
            feedbacks[managed],
            feedbacks[account],
            feedbacks[override],
        ]


def test_feedback_table_default_columns():
    assert FeedbackTable.default_columns == ("talk", "review", "speaker")
