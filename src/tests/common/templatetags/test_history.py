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


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    (
        (Submission._meta.get_field("event"), None),
        (Submission._meta.get_field("event"), ""),
        (Submission._meta.get_field("event"), 0),
        (Submission._meta.get_field("event"), 99999),
        (db_models.CharField(), "some_value"),
    ),
    ids=("none", "empty", "zero", "missing_pk", "non_fk_field"),
)
def test_resolve_foreign_key_passes_through_unresolvable_values(field, value):
    assert resolve_foreign_key(field, value) == value


@pytest.mark.django_db
def test_resolve_foreign_key_resolves_fk():
    event = EventFactory()
    field = Submission._meta.get_field("event")
    result = resolve_foreign_key(field, event.pk)
    assert result == str(event)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (
        (UserApiToken._meta.get_field("limit_events"), None, None),
        (UserApiToken._meta.get_field("limit_events"), [], []),
        (UserApiToken._meta.get_field("limit_events"), [99999], "99999"),
        (db_models.CharField(), ["some_value"], ["some_value"]),
    ),
    ids=("none", "empty", "missing_pk", "non_m2m_field"),
)
def test_resolve_many_to_many_without_resolvable_objects(field, value, expected):
    assert resolve_many_to_many(field, value) == expected


@pytest.mark.django_db
def test_resolve_many_to_many_resolves_pks():
    events = [EventFactory(), EventFactory()]
    field = UserApiToken._meta.get_field("limit_events")

    result = resolve_many_to_many(field, [event.pk for event in events])

    assert result == f"{events[0]}, {events[1]}"


@pytest.mark.django_db
def test_get_display_returns_choice_label():
    submission = SubmissionFactory(state=SubmissionStates.SUBMITTED)
    result = get_display(submission, "state", SubmissionStates.ACCEPTED)
    assert result == "accepted"
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_history_tab_groups_entries_and_takes_presentation_from_context(event):
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)
    request = RequestFactory().get("/")

    plain = history_tab({"request": request, "history_log_entries": [log]})
    presented = history_tab(
        {
            "request": request,
            "history_log_entries": [log],
            "history_with_objects": True,
            "history_show_event": True,
        }
    )

    entries = [
        entry for group in plain["activity_groups"] for entry in group["entries"]
    ]
    assert [entry["log"] for entry in entries] == [log]
    assert plain["request"] == request
    assert entries[0]["object_url"] == ""
    assert plain["show_event"] is False
    assert presented["show_event"] is True
    entry = presented["activity_groups"][0]["entries"][0]
    assert entry["object_url"] == submission.orga_urls.base


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("key", "make_change", "has_diff"),
    (
        (
            "title",
            lambda event, other: (
                {"old": "hello world", "new": "hello there", "field": None},
                ("hello world", "hello there"),
            ),
            True,
        ),
        (
            "is_featured",
            lambda event, other: (
                {
                    "old": False,
                    "new": True,
                    "field": Submission._meta.get_field("is_featured"),
                },
                (BooleanColumn.FALSE_MARK, BooleanColumn.TRUE_MARK),
            ),
            False,
        ),
        (
            "event",
            lambda event, other: (
                {
                    "old": event.pk,
                    "new": other.pk,
                    "old_display": str(event),
                    "new_display": str(other),
                    "field": Submission._meta.get_field("event"),
                },
                (str(event), str(other)),
            ),
            False,
        ),
        (
            "limit_events",
            lambda event, other: (
                {
                    "old": [event.pk],
                    "new": [event.pk, other.pk],
                    "old_display": str(event),
                    "new_display": f"{event}, {other}",
                    "field": UserApiToken._meta.get_field("limit_events"),
                },
                (str(event), f"{event}, {other}"),
            ),
            False,
        ),
        (
            "state",
            lambda event, other: (
                {
                    "old": SubmissionStates.SUBMITTED,
                    "new": SubmissionStates.ACCEPTED,
                    "field": None,
                },
                ("submitted", "accepted"),
            ),
            False,
        ),
    ),
    ids=("text", "boolean", "foreign_key", "many_to_many", "choices"),
)
def test_change_row_renders_one_row_per_scalar_change(
    event, key, make_change, has_diff
):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    log = ActivityLogFactory(event=event, content_object=submission)
    other_event = EventFactory()
    request = RequestFactory().get("/")
    request.event = event
    change, (old_display, new_display) = make_change(event, other_event)
    change.update({"question": None, "label": "Label"})

    result = change_row({"request": request}, key, change, log)

    assert result["field"] == key
    assert [
        (row["label"], row["old"], row["new"], "diff_data" in row)
        for row in result["rows"]
    ] == [("Label", old_display, new_display, has_diff)]


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
