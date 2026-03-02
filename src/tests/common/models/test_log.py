import pytest
from django.utils.html import escape
from django_scopes import scopes_disabled

from pretalx.common.log_display import LOG_NAMES
from pretalx.common.models.log import ActivityLog
from pretalx.submission.models import Submission
from tests.factories import (
    ActivityLogFactory,
    QuestionFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_activitylog_str():
    log = ActivityLogFactory()

    result = str(log)

    assert result == (
        f"ActivityLog(event={log.event.slug}, person={log.person.name}, "
        f"content_object={log.content_object}, action_type={log.action_type})"
    )


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_activitylog_display_known_action_type():
    """When a signal handler recognises the action_type, display returns the
    human-readable string."""
    log = ActivityLogFactory(action_type="pretalx.submission.create")

    result = log.display

    assert result == LOG_NAMES["pretalx.submission.create"]


@pytest.mark.django_db
def test_activitylog_display_unknown_action_falls_back_to_action_type():
    """When no signal handler recognises the action_type, display returns the
    raw action_type string."""
    log = ActivityLogFactory(action_type="pretalx.totally.unknown.action")

    result = log.display

    assert result == "pretalx.totally.unknown.action"


@pytest.mark.django_db
def test_activitylog_display_object_without_content_object():
    """When content_object is None, display_object returns empty string."""
    with scopes_disabled():
        submission = SubmissionFactory()
    log = ActivityLogFactory(content_object=submission, event=submission.event)
    # Delete the submission so content_object resolves to None
    with scopes_disabled():
        submission.delete()
    # Clear Django's generic FK cache so it re-fetches
    log.refresh_from_db()

    result = log.display_object

    assert result == ""


@pytest.mark.django_db
def test_activitylog_changes_returns_none_without_data():
    log = ActivityLogFactory(data=None)

    assert log.changes is None


@pytest.mark.django_db
def test_activitylog_changes_returns_none_without_event():
    log = ActivityLogFactory(
        event=None, data={"changes": {"title": {"old": "A", "new": "B"}}}
    )

    assert log.changes is None


@pytest.mark.django_db
def test_activitylog_changes_returns_none_without_changes_key():
    log = ActivityLogFactory(data={"some_key": "some_value"})

    assert log.changes is None


@pytest.mark.django_db
def test_activitylog_changes_skips_empty_old_and_new():
    log = ActivityLogFactory(data={"changes": {"title": {"old": None, "new": None}}})

    with scopes_disabled():
        result = log.changes

    assert result == {}


@pytest.mark.django_db
def test_activitylog_changes_parses_field_changes():
    """When content_object exists and changes reference model fields, the
    changes dict contains field metadata."""
    with scopes_disabled():
        submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "Old Title", "new": "New Title"}}},
    )
    title_field = Submission._meta.get_field("title")

    with scopes_disabled():
        result = log.changes

    assert result == {
        "title": {
            "old": "Old Title",
            "new": "New Title",
            "field": title_field,
            "label": title_field.verbose_name,
        }
    }


@pytest.mark.django_db
def test_activitylog_changes_unknown_field_uses_capitalized_key():
    with scopes_disabled():
        submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"nonexistent_field": {"old": "a", "new": "b"}}},
    )

    with scopes_disabled():
        result = log.changes

    assert result == {
        "nonexistent_field": {"old": "a", "new": "b", "label": "Nonexistent_field"}
    }


@pytest.mark.django_db
def test_activitylog_changes_question_key():
    with scopes_disabled():
        question = QuestionFactory()
    log = ActivityLogFactory(
        event=question.event,
        data={
            "changes": {f"question-{question.pk}": {"old": "answer1", "new": "answer2"}}
        },
    )

    with scopes_disabled():
        result = log.changes

    assert result == {
        f"question-{question.pk}": {
            "old": "answer1",
            "new": "answer2",
            "question": question,
            "label": question.question,
        }
    }


@pytest.mark.django_db
def test_activitylog_changes_question_key_nonexistent():
    """When a question-N key references a deleted question, the result only
    contains old/new values without question metadata."""
    log = ActivityLogFactory(
        data={"changes": {"question-99999": {"old": "a", "new": "b"}}}
    )

    with scopes_disabled():
        result = log.changes

    assert result == {"question-99999": {"old": "a", "new": "b"}}


@pytest.mark.django_db
def test_activitylog_changes_returns_none_when_content_object_deleted():
    """When the content_object has been deleted (content_object resolves to
    None), changes returns None."""
    with scopes_disabled():
        submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "A", "new": "B"}}},
    )
    with scopes_disabled():
        submission.delete()

    with scopes_disabled():
        result = log.changes

    assert result is None


@pytest.mark.django_db
def test_activitylog_display_object_with_known_content_object():
    """When display_object has a recognised content_object, it returns
    the formatted link string."""
    with scopes_disabled():
        submission = SubmissionFactory()
    log = ActivityLogFactory(content_object=submission, event=submission.event)

    with scopes_disabled():
        result = log.display_object

    assert result == (
        f'Proposal <a href="{submission.orga_urls.base}">{escape(submission.title)}</a>'
    )


@pytest.mark.django_db
def test_activitylog_display_object_unhandled_type_returns_empty():
    """When no signal handler recognises the content_object type, display_object
    returns empty string."""
    with scopes_disabled():
        track = TrackFactory()
    log = ActivityLogFactory(content_object=track, event=track.event)

    with scopes_disabled():
        result = log.display_object

    assert result == ""


@pytest.mark.django_db
def test_activitylog_changes_with_many_to_one_rel():
    """Changes on a field that is a reverse relation (ManyToOneRel) use the
    related model's verbose_name_plural as label."""
    with scopes_disabled():
        submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"reviews": {"old": "1", "new": "2"}}},
    )
    reviews_field = Submission._meta.get_field("reviews")

    with scopes_disabled():
        result = log.changes

    assert result == {
        "reviews": {
            "old": "1",
            "new": "2",
            "field": reviews_field,
            "label": reviews_field.related_model._meta.verbose_name_plural,
        }
    }


@pytest.mark.django_db
def test_activitylog_ordering():
    """ActivityLogs are ordered by -timestamp (newest first)."""
    log1 = ActivityLogFactory()
    log2 = ActivityLogFactory(event=log1.event)

    with scopes_disabled():
        logs = list(log1.event.log_entries.all())

    assert logs == [log2, log1]
