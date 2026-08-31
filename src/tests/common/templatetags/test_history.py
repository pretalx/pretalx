# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms
from django.db import models as db_models
from django.test import RequestFactory
from django.utils import translation

from pretalx.common.log import resolve_foreign_key, resolve_many_to_many
from pretalx.common.tables import BooleanColumn
from pretalx.common.templatetags.history import (
    change_row,
    form_field_choices,
    get_display,
    history_tab,
    render_boolean,
    resolve_choices,
)
from pretalx.event.models import Event
from pretalx.person.models import UserApiToken
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    SubmissionFactory,
    UserFactory,
)

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
def test_history_tab_groups_context_entries(event):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    context = {"request": request, "history_log_entries": [log]}

    result = history_tab(context)

    entries = [
        entry for group in result["activity_groups"] for entry in group["entries"]
    ]
    assert len(entries) == 1
    assert entries[0]["log"] == log
    assert result["request"] == request
    assert entries[0]["object_url"] == ""
    assert result["show_event"] is False


@pytest.mark.django_db
def test_history_tab_takes_presentation_from_context(event):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    context = {
        "request": RequestFactory().get("/"),
        "history_log_entries": [log],
        "history_with_objects": True,
        "history_show_event": True,
    }

    result = history_tab(context)

    assert result["show_event"] is True
    entry = result["activity_groups"][0]["entries"][0]
    assert entry["object_url"] == submission.orga_urls.base


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
        "old_display": str(event),
        "new_display": str(event),
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
        "old_display": str(event),
        "new_display": f"{event}, {other_event}",
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
@pytest.mark.parametrize(
    ("old", "new"),
    (("Hello", {"en": "Hi"}), ({"en": "Hello"}, "Bye")),
    ids=("string-old", "string-new"),
)
def test_change_row_dict_with_string_uses_event_locale(event, old, new):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {"question": None, "old": old, "new": new, "field": None, "label": "Title"}
    result = change_row(context, "title", change, log)
    assert len(result["rows"]) == 1
    languages = {row["language"] for row in result["rows"]}
    assert languages == {"en"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("new", "expected"),
    (({"en": "Hi"}, {"en"}), ({"en": "Hi", "de": "Hallo"}, {"en", "de"})),
    ids=("single-locale", "active-language"),
)
def test_change_row_dict_with_string_without_event(new, expected):
    user = UserFactory()
    log = ActivityLogFactory(event=None, content_object=user)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = None
    context = {"request": request}

    change = {
        "question": None,
        "old": "Hello",
        "new": new,
        "field": None,
        "label": "Name",
    }
    with translation.override("de"):
        result = change_row(context, "name", change, log)

    assert {row["language"] for row in result["rows"]} == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("change_label", "expected"),
    ((None, "Unknown_field"), ("headline", "Headline")),
    ids=("field-name-fallback", "capitalised"),
)
def test_change_row_label(event, change_label, expected):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": "a",
        "new": "b",
        "field": None,
        "label": change_label,
    }
    result = change_row(context, "unknown_field", change, log)
    assert result["rows"][0]["label"] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (("median", "Median"), ("gone", "gone"), (["median", "mean"], "Median, Mean")),
)
def test_resolve_choices(value, expected):
    assert resolve_choices({"median": "Median", "mean": "Mean"}, value) == expected


@pytest.mark.parametrize(
    ("field", "expected"),
    (
        (forms.ChoiceField(choices=(("median", "Median"),)), {"median": "Median"}),
        (forms.ChoiceField(), {}),
        (forms.BooleanField(), {}),
        (forms.ModelChoiceField(queryset=Event.objects.all()), {}),
    ),
    ids=("choices", "runtime-choices", "other-field", "model-choices"),
)
def test_form_field_choices(field, expected):
    assert form_field_choices(field) == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    (
        "key",
        "label",
        "form_field",
        "old",
        "new",
        "expected_old",
        "expected_new",
        "has_diff",
    ),
    (
        (
            "feature_flags.use_tracks",
            "Use tracks",
            forms.BooleanField(),
            False,
            True,
            BooleanColumn.FALSE_MARK,
            BooleanColumn.TRUE_MARK,
            False,
        ),
        (
            "review_settings.aggregate_method",
            "Score aggregation method",
            forms.ChoiceField(
                choices=(("median", "Median"), ("mean", "Average (mean)"))
            ),
            "median",
            "mean",
            "Median",
            "Average (mean)",
            False,
        ),
        (
            "display_settings.heading_font",
            "Heading font",
            forms.ChoiceField(),
            "Fira Sans",
            "Roboto",
            "Fira Sans",
            "Roboto",
            True,
        ),
        (
            "attendee_signup_settings.signup_domains",
            "Allowed email domains",
            None,
            ["a.org", "b.org"],
            [],
            "a.org, b.org",
            "",
            False,
        ),
    ),
    ids=("boolean", "choice", "runtime-choices", "list"),
)
def test_change_row_settings_form_field(
    event, key, label, form_field, old, new, expected_old, expected_new, has_diff
):
    log = ActivityLogFactory(event=event, content_object=event)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": old,
        "new": new,
        "field": None,
        "label": label,
        "form_field": form_field,
    }
    result = change_row(context, key, change, log)

    row = result["rows"][0]
    assert row["label"] == label
    assert row["old"] == expected_old
    assert row["new"] == expected_new
    assert ("diff_data" in row) is has_diff


@pytest.mark.django_db
def test_change_row_uses_supplied_choices(event):
    log = ActivityLogFactory(event=event, content_object=event)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": ["en"],
        "new": ["en", "de"],
        "label": "Content languages",
        "choices": {"en": "English", "de": "Deutsch"},
    }
    row = change_row(context, "content_locales", change, log)["rows"][0]

    assert row["old"] == "English"
    assert row["new"] == "English, Deutsch"


@pytest.mark.django_db
def test_change_row_file_field_is_preformatted(event):
    log = ActivityLogFactory(event=event, content_object=event)

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    context = {"request": request}

    change = {
        "question": None,
        "old": "# header {\n}",
        "new": "# header {\n  color: red;\n}",
        "field": Event._meta.get_field("custom_css"),
    }
    row = change_row(context, "custom_css", change, log)["rows"][0]

    assert row["preformatted"] is True
    assert "<h1" not in str(row["diff_data"]["new_html"])
