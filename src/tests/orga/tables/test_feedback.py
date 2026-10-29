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


def test_feedback_table_talk_column_follows_include_talk(event):
    feedback = FeedbackFactory(talk__event=event)
    user = UserFactory.build()

    default = FeedbackTable([feedback], event=event, user=user)
    without_talk = FeedbackTable([feedback], event=event, user=user, include_talk=False)

    assert "talk" not in default.exclude
    assert "talk" in without_talk.exclude


def test_feedback_table_render_review_as_markdown(event):
    markdown = FeedbackFactory(talk__event=event, review="**bold text**")
    empty = FeedbackFactory(talk__event=event, review="")
    table = FeedbackTable([markdown, empty], event=event, user=UserFactory.build())

    assert table.render_review(markdown) == "<p><strong>bold text</strong></p>"
    assert table.render_review(empty) == ""


def test_feedback_table_speaker_column_uses_display_name(event):
    managed = SpeakerFactory(event=event, user=None, name="Anna")
    account = SpeakerFactory(event=event, user__name="Mia")
    override = SpeakerFactory(event=event, user__name="Bea", name="Zoe")
    feedbacks = {
        speaker: FeedbackFactory(talk__event=event, speaker=speaker)
        for speaker in (managed, account, override)
    }
    table = FeedbackTable(
        list(feedbacks.values()), event=event, user=UserFactory.build()
    )

    assert table.render_speaker(managed) == "Anna"
    assert table.render_speaker(account) == "Mia"
    assert table.render_speaker(override) == "Zoe"

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
