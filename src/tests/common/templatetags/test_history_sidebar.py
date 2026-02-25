import pytest
from django.db import models as db_models
from django.test import RequestFactory
from django_scopes import scopes_disabled

from pretalx.common.tables import BooleanColumn
from pretalx.common.templatetags.history_sidebar import (
    change_row,
    get_display,
    history_sidebar,
    render_boolean,
    resolve_foreign_key,
)
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import ActivityLogFactory, EventFactory, SubmissionFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    ((True, BooleanColumn.TRUE_MARK), (False, BooleanColumn.FALSE_MARK)),
)
def test_render_boolean(value, expected):
    assert render_boolean(value) == expected


@pytest.mark.parametrize("value", (None, "", 0))
def test_resolve_foreign_key_falsy_value(value):
    """Falsy values are returned as-is regardless of field type."""
    field = db_models.ForeignKey(to="event.Event", on_delete=db_models.CASCADE)
    assert resolve_foreign_key(field, value) == value


def test_resolve_foreign_key_non_fk_field():
    """Non-ForeignKey fields return the value unchanged."""
    field = db_models.CharField()
    assert resolve_foreign_key(field, "some_value") == "some_value"


@pytest.mark.django_db
def test_resolve_foreign_key_resolves_fk():
    """ForeignKey field resolves PK to the related model's string representation."""
    event = EventFactory()
    field = Submission._meta.get_field("event")
    result = resolve_foreign_key(field, event.pk)
    assert result == str(event)


@pytest.mark.django_db
def test_resolve_foreign_key_missing_pk():
    """ForeignKey with nonexistent PK returns the value unchanged."""
    field = Submission._meta.get_field("event")
    assert resolve_foreign_key(field, 99999) == 99999


@pytest.mark.django_db
def test_get_display_returns_choice_label():
    """get_display returns the human-readable label for a choices field."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.SUBMITTED)
    result = get_display(submission, "state", SubmissionStates.ACCEPTED)
    assert result == "accepted"
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_history_sidebar_returns_entries(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    context = {"request": request}

    with scopes_disabled():
        result = history_sidebar(context, submission)

    assert len(result["entries"]) == 1
    assert result["entries"][0] == log
    assert result["object"] == submission
    assert result["request"] == request
    assert result["show_details_link"] is True
    assert result["show_more_link"] is False
    assert result["history_class"] == "history-sidebar"
    assert result["show_history_title"] is True


@pytest.mark.django_db
def test_history_sidebar_respects_limit(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        for _ in range(3):
            ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    context = {"request": rf.get("/")}

    with scopes_disabled():
        result = history_sidebar(context, submission, limit=2)

    assert len(result["entries"]) == 2
    assert result["show_more_link"] is True


@pytest.mark.django_db
def test_history_sidebar_no_limit(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    context = {"request": rf.get("/")}

    with scopes_disabled():
        result = history_sidebar(context, submission, limit=0)

    assert len(result["entries"]) == 1
    assert result["show_more_link"] is False


@pytest.mark.django_db
def test_change_row_simple_text_change(event):
    """Simple text change produces a diff result."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": "hello world",
        "new": "hello there",
        "field": None,
        "label": "Title",
    }
    result = change_row(context, "title", change, log)

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["label"] == "Title"
    assert row["old"] == "hello world"
    assert row["new"] == "hello there"
    assert "diff_data" in row
    assert result["field"] == "title"


@pytest.mark.django_db
def test_change_row_boolean_field(event):
    """BooleanField values are rendered as check/cross icons."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    bool_field = Submission._meta.get_field("is_featured")
    change = {
        "question": None,
        "old": False,
        "new": True,
        "field": bool_field,
        "label": "Featured",
    }
    result = change_row(context, "is_featured", change, log)

    row = result["rows"][0]
    assert row["old"] == BooleanColumn.FALSE_MARK
    assert row["new"] == BooleanColumn.TRUE_MARK


@pytest.mark.django_db
def test_change_row_fk_field(event):
    """ForeignKey values are resolved to their string representation."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    fk_field = Submission._meta.get_field("event")
    change = {
        "question": None,
        "old": event.pk,
        "new": event.pk,
        "field": fk_field,
        "label": "Event",
    }
    result = change_row(context, "event", change, log)

    row = result["rows"][0]
    assert row["old"] == str(event)
    assert row["new"] == str(event)


@pytest.mark.django_db
def test_change_row_dict_values(event):
    """Dict values (i18n) produce one row per language."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": {"en": "Hello", "de": "Hallo"},
        "new": {"en": "Hi", "de": "Hallo"},
        "field": None,
        "label": "Title",
    }
    result = change_row(context, "title", change, log)

    assert len(result["rows"]) == 2
    assert result["rows"][0]["label"] == "Title"
    assert result["rows"][0]["rowspan"] == 2
    languages = {row["language"] for row in result["rows"]}
    assert languages == {"en", "de"}


@pytest.mark.django_db
def test_change_row_choices_field(event):
    """Field with get_{field}_display resolves choice values."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": SubmissionStates.SUBMITTED,
        "new": SubmissionStates.ACCEPTED,
        "field": None,
        "label": "State",
    }
    result = change_row(context, "state", change, log)

    row = result["rows"][0]
    assert row["old"] == "submitted"
    assert row["new"] == "accepted"


@pytest.mark.django_db
def test_change_row_label_from_field_verbose_name(event):
    """When no label and no question but field_obj exists, use its verbose_name."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    bool_field = Submission._meta.get_field("is_featured")
    change = {"question": None, "old": False, "new": True, "field": bool_field}
    result = change_row(context, "is_featured", change, log)
    assert result["rows"][0]["label"] == "is_featured"


@pytest.mark.django_db
def test_change_row_dict_with_string_old(event):
    """When new is dict but old is string, old is wrapped in a single-locale dict."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": "Hello",
        "new": {"en": "Hi"},
        "field": None,
        "label": "Title",
    }
    result = change_row(context, "title", change, log)
    assert len(result["rows"]) == 1
    languages = {row["language"] for row in result["rows"]}
    assert languages == {"en"}


@pytest.mark.django_db
def test_change_row_dict_with_string_new(event):
    """When old is dict but new is string, new is wrapped in a single-locale dict."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": {"en": "Hello"},
        "new": "Bye",
        "field": None,
        "label": "Title",
    }
    result = change_row(context, "title", change, log)
    assert len(result["rows"]) == 1
    languages = {row["language"] for row in result["rows"]}
    assert languages == {"en"}


@pytest.mark.django_db
def test_change_row_label_falls_back_to_field_name(event):
    """When no label and no question, the field name is used as label."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {"question": None, "old": "a", "new": "b", "field": None}
    result = change_row(context, "unknown_field", change, log)
    assert result["rows"][0]["label"] == "unknown_field"
