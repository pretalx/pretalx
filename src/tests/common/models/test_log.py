# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.urls import reverse
from django.utils.html import escape

from pretalx.common.log import LOG_NAMES
from pretalx.common.models.log import ActivityLog
from pretalx.submission.models import Submission
from tests.factories import (
    ActivityLogFactory,
    QuestionFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_activitylog_str():
    log = ActivityLogFactory()

    result = str(log)

    assert result == (
        f"ActivityLog(event={log.event.slug}, person={log.person.name}, "
        f"content_object={log.content_object}, action_type={log.action_type})"
    )


def test_activitylog_str_without_event_or_person():
    log = ActivityLogFactory(event=None, person=None)

    result = str(log)

    assert result == (
        f"ActivityLog(event=None, person=None, "
        f"content_object={log.content_object}, action_type={log.action_type})"
    )


def test_activitylog_json_data_returns_data():
    log = ActivityLog(data={"key": "value"})

    assert log.json_data == {"key": "value"}


def test_activitylog_json_data_returns_empty_dict_for_none():
    log = ActivityLog(data=None)

    assert log.json_data == {}


def test_activitylog_display_known_action_type():
    log = ActivityLogFactory(action_type="pretalx.submission.create")

    result = log.display

    assert result == LOG_NAMES["pretalx.submission.create"]


def test_activitylog_display_unknown_action_falls_back_to_action_type():
    log = ActivityLogFactory(action_type="pretalx.totally.unknown.action")

    result = log.display

    assert result == "pretalx.totally.unknown.action"


def test_activitylog_display_object_without_content_object():
    submission = SubmissionFactory()
    log = ActivityLogFactory(content_object=submission, event=submission.event)
    # Delete the submission so content_object resolves to None
    submission.delete()
    # Clear Django's generic FK cache so it re-fetches
    log.refresh_from_db()

    result = log.display_object

    assert result == ""


def test_activitylog_changes_returns_none_without_data():
    log = ActivityLogFactory(data=None)

    assert log.changes is None


def test_activitylog_detail_url_with_event():
    log = ActivityLogFactory()

    assert log.detail_url == reverse(
        "orga:event.history.detail", kwargs={"event": log.event.slug, "pk": log.pk}
    )


def test_activitylog_detail_url_without_event():
    log = ActivityLogFactory(event=None)

    assert log.detail_url == reverse("orga:admin.log.detail", kwargs={"pk": log.pk})


def test_activitylog_changes_returns_none_without_changes_key():
    log = ActivityLogFactory(data={"some_key": "some_value"})

    assert log.changes is None


def test_activitylog_changes_skips_empty_old_and_new():
    log = ActivityLogFactory(data={"changes": {"title": {"old": None, "new": None}}})

    result = log.changes

    assert result == {}


def test_activitylog_changes_parses_field_changes():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "Old Title", "new": "New Title"}}},
    )
    title_field = Submission._meta.get_field("title")

    result = log.changes

    assert result == {
        "title": {
            "old": "Old Title",
            "new": "New Title",
            "field": title_field,
            "label": title_field.verbose_name,
        }
    }


def test_activitylog_changes_unknown_field_uses_capitalized_key():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"nonexistent_field": {"old": "a", "new": "b"}}},
    )

    result = log.changes

    assert result == {
        "nonexistent_field": {"old": "a", "new": "b", "label": "Nonexistent_field"}
    }


def test_activitylog_changes_question_key():
    question = QuestionFactory()
    log = ActivityLogFactory(
        event=question.event,
        data={
            "changes": {f"question-{question.pk}": {"old": "answer1", "new": "answer2"}}
        },
    )

    result = log.changes

    assert result == {
        f"question-{question.pk}": {
            "old": "answer1",
            "new": "answer2",
            "question": question,
            "label": question.question,
        }
    }


def test_activitylog_changes_question_key_nonexistent():
    log = ActivityLogFactory(
        data={"changes": {"question-99999": {"old": "a", "new": "b"}}}
    )

    result = log.changes

    assert result == {"question-99999": {"old": "a", "new": "b"}}


def test_activitylog_changes_returns_none_when_content_object_deleted():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "A", "new": "B"}}},
    )
    submission.delete()

    result = log.changes

    assert result is None


def test_activitylog_display_object_with_known_content_object():
    submission = SubmissionFactory()
    log = ActivityLogFactory(content_object=submission, event=submission.event)

    result = log.display_object

    assert result == (
        f'Proposal <a href="{submission.orga_urls.base}">{escape(submission.title)}</a>'
    )


def test_activitylog_display_object_unhandled_type_returns_empty():
    track = TrackFactory()
    log = ActivityLogFactory(content_object=track, event=track.event)

    result = log.display_object

    assert result == ""


def test_activitylog_changes_with_many_to_one_rel():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"reviews": {"old": "1", "new": "2"}}},
    )
    reviews_field = Submission._meta.get_field("reviews")

    result = log.changes

    assert result == {
        "reviews": {
            "old": "1",
            "new": "2",
            "field": reviews_field,
            "label": reviews_field.related_model._meta.verbose_name_plural,
        }
    }


def test_activitylog_ordering():
    log1 = ActivityLogFactory()
    log2 = ActivityLogFactory(event=log1.event)

    logs = list(log1.event.log_entries.all())

    assert logs == [log2, log1]
