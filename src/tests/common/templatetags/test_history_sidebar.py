# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.db import models as db_models
from django.test import RequestFactory

from pretalx.common.tables import BooleanColumn
from pretalx.common.templatetags.history_sidebar import (
    change_row,
    get_display,
    history_sidebar,
    render_boolean,
    resolve_foreign_key,
    resolve_many_to_many,
)
from pretalx.person.models import UserApiToken
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
    field = db_models.ForeignKey(to="event.Event", on_delete=db_models.CASCADE)
    assert resolve_foreign_key(field, value) == value


def test_resolve_foreign_key_non_fk_field():
    field = db_models.CharField()
    assert resolve_foreign_key(field, "some_value") == "some_value"


@pytest.mark.django_db
def test_resolve_foreign_key_resolves_fk():
    event = EventFactory()
    field = Submission._meta.get_field("event")
    result = resolve_foreign_key(field, event.pk)
    assert result == str(event)


@pytest.mark.django_db
def test_resolve_foreign_key_missing_pk():
    field = Submission._meta.get_field("event")
    assert resolve_foreign_key(field, 99999) == 99999


@pytest.mark.parametrize("value", (None, []))
def test_resolve_many_to_many_falsy_value(value):
    field = UserApiToken._meta.get_field("limit_events")
    assert resolve_many_to_many(field, value) == value


def test_resolve_many_to_many_non_m2m_field():
    field = db_models.CharField()
    assert resolve_many_to_many(field, ["some_value"]) == ["some_value"]


@pytest.mark.django_db
def test_resolve_many_to_many_resolves_pks():
    events = [EventFactory(), EventFactory()]
    field = UserApiToken._meta.get_field("limit_events")

    result = resolve_many_to_many(field, [event.pk for event in events])

    assert result == f"{events[0]}, {events[1]}"


@pytest.mark.django_db
def test_resolve_many_to_many_missing_pk():
    field = UserApiToken._meta.get_field("limit_events")
    assert resolve_many_to_many(field, [99999]) == "99999"


@pytest.mark.django_db
def test_get_display_returns_choice_label():
    submission = SubmissionFactory(state=SubmissionStates.SUBMITTED)
    result = get_display(submission, "state", SubmissionStates.ACCEPTED)
    assert result == "accepted"
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_history_sidebar_returns_entries(event):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    context = {"request": request}

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
    submission = SubmissionFactory(event=event)
    for _ in range(3):
        ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    context = {"request": rf.get("/")}

    result = history_sidebar(context, submission, limit=2)

    assert len(result["entries"]) == 2
    assert result["show_more_link"] is True


@pytest.mark.django_db
def test_history_sidebar_no_limit(event):
    submission = SubmissionFactory(event=event)
    ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    context = {"request": rf.get("/")}

    result = history_sidebar(context, submission, limit=0)

    assert len(result["entries"]) == 1
    assert result["show_more_link"] is False


@pytest.mark.django_db
def test_change_row_simple_text_change(event):
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
def test_change_row_m2m_field(event):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    other_event = EventFactory()
    m2m_field = UserApiToken._meta.get_field("limit_events")
    change = {
        "question": None,
        "old": [event.pk],
        "new": [event.pk, other_event.pk],
        "field": m2m_field,
        "label": "Events",
    }
    result = change_row(context, "limit_events", change, log)

    row = result["rows"][0]
    assert row["old"] == str(event)
    assert row["new"] == f"{event}, {other_event}"


@pytest.mark.django_db
def test_change_row_dict_values(event):
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
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {"question": None, "old": "a", "new": "b", "field": None}
    result = change_row(context, "unknown_field", change, log)
    assert result["rows"][0]["label"] == "unknown_field"
