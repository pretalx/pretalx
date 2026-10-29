# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.html import escape
from django_scopes import scopes_disabled

from pretalx.common.log import LOG_NAMES
from pretalx.common.models.log import ActivityLog
from pretalx.submission.models import Submission
from tests.factories import (
    ActivityLogFactory,
    AvailabilityFactory,
    EventFactory,
    QuestionFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_activitylog_str():
    log = ActivityLogFactory()
    bare = ActivityLogFactory(event=None, person=None)

    assert str(log) == (
        f"ActivityLog(event={log.event.slug}, person={log.person.name}, "
        f"content_object={log.content_object}, action_type={log.action_type})"
    )
    assert str(bare) == (
        f"ActivityLog(event=None, person=None, "
        f"content_object={bare.content_object}, action_type={bare.action_type})"
    )


@pytest.mark.parametrize(
    ("data", "expected"), (({"key": "value"}, {"key": "value"}), (None, {}))
)
def test_activitylog_json_data(data, expected):
    assert ActivityLog(data=data).json_data == expected


@pytest.mark.parametrize(
    ("action_type", "expected"),
    (
        ("pretalx.submission.create", LOG_NAMES["pretalx.submission.create"]),
        ("pretalx.totally.unknown.action", "pretalx.totally.unknown.action"),
    ),
    ids=("known", "unknown_falls_back_to_action_type"),
)
def test_activitylog_display(action_type, expected):
    log = ActivityLogFactory(action_type=action_type)

    assert log.display == expected


def test_activitylog_deleted_content_object_has_no_display_or_changes():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "A", "new": "B"}}},
    )
    # Delete the submission so content_object resolves to None
    submission.delete()
    # Clear Django's generic FK cache so it re-fetches
    log.refresh_from_db()

    assert log.display_object == ""
    assert log.changes is None


def test_activitylog_content_object_none_for_uninstalled_model():
    stale_type = ContentType.objects.create(app_label="ghost_plugin", model="ghost")
    event = EventFactory()
    with scopes_disabled():
        log = ActivityLog.objects.create(
            event=event,
            content_type=stale_type,
            object_id=1,
            action_type="pretalx.submission.update",
            data={"changes": {"title": {"old": "A", "new": "B"}}},
        )

    assert log.content_object is None
    assert log.display_object == ""
    assert log.changes is None
    assert log.display == LOG_NAMES["pretalx.submission.update"]


def test_activitylog_content_object_none_without_content_type():
    assert ActivityLog().content_object is None


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        (None, None),
        ({"some_key": "some_value"}, None),
        ({"changes": {"title": {"old": None, "new": None}}}, {}),
    ),
    ids=("no_data", "no_changes_key", "empty_old_and_new"),
)
def test_activitylog_changes_without_usable_changes(data, expected):
    log = ActivityLogFactory(data=data)

    assert log.changes == expected


def test_activitylog_detail_url():
    log = ActivityLogFactory()
    global_log = ActivityLogFactory(event=None)

    assert log.detail_url == reverse(
        "orga:event.history.detail", kwargs={"event": log.event.slug, "pk": log.pk}
    )
    assert global_log.detail_url == reverse(
        "orga:admin.log.detail", kwargs={"pk": global_log.pk}
    )


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


def test_activitylog_display_object_with_known_content_object():
    submission = SubmissionFactory()
    log = ActivityLogFactory(content_object=submission, event=submission.event)

    result = log.display_object

    assert result == (
        f'Proposal <a href="{submission.orga_urls.base}">{escape(submission.title)}</a>'
    )


def test_activitylog_display_object_unlinkable_type_returns_empty():
    availability = AvailabilityFactory()
    log = ActivityLogFactory(content_object=availability, event=availability.event)

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
