# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.forms.exports import TableExportForm
from pretalx.common.models.exports import TableExport
from pretalx.orga.tables.cfp import TrackTable
from pretalx.orga.tables.submission import SubmissionTable
from tests.factories import EventFactory, TableExportFactory, UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _data(**overrides):
    data = QueryDict(mutable=True)
    data.update({"serializer": "csv"})
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        elif isinstance(value, list):
            data.setlist(key, value)
        else:
            data[key] = value
    return data


def test_export_form_builds_config_from_toolbar_submission(event):
    user = make_orga_user(event, can_change_submissions=True)
    data = _data(
        filters="?state=accepted&sort=state&page=3",
        columns=["title", "abstract", "indicator", "bogus"],
        ordering=["-title"],
        csv_list_delimiter="comma",
    )

    form = TableExportForm(
        data=data, event=event, user=user, table_class=SubmissionTable
    )

    assert form.is_valid(), form.errors
    assert form.save(commit=False).config == {
        "table": "SubmissionTable",
        "columns": ["title", "abstract"],
        "ordering": ["-title"],
        "filters": {"state": ["accepted"]},
        "serializer": "csv",
        "serializer_options": {"delimiter": "", "list_delimiter": "comma"},
    }


@pytest.mark.parametrize(
    ("stored", "data", "expected"),
    (
        (None, {"filters": ""}, {"state": ["submitted", "accepted", "confirmed"]}),
        ({}, {}, {}),
    ),
    ids=("toolbar_resolves_list_defaults", "editor_keeps_stored_empty_filters"),
)
def test_export_form_applies_list_defaults_only_from_list_url(
    event, stored, data, expected
):
    user = make_orga_user(event, can_change_submissions=True)
    kwargs = {}
    if stored is not None:
        kwargs["instance"] = TableExportFactory(event=event, filters=stored)

    form = TableExportForm(
        data=_data(**data),
        event=event,
        user=user,
        table_class=SubmissionTable,
        **kwargs,
    )

    assert form.is_valid(), form.errors
    assert form.filters == expected


@pytest.mark.parametrize(
    ("stored", "preselected"),
    ((None, ["submitted", "accepted", "confirmed"]), ({}, [])),
    ids=("create", "edit_unfiltered"),
)
def test_export_form_preselects_list_defaults_only_without_stored_config(
    event, stored, preselected
):
    user = make_orga_user(event, can_change_submissions=True)
    kwargs = {} if stored is None else {"instance": TableExportFactory(filters=stored)}

    form = TableExportForm(
        event=event, user=user, table_class=SubmissionTable, **kwargs
    )

    assert form.filterset.values["state"] == preselected


def test_export_form_ordering_from_live_table(event):
    user = make_orga_user(event, can_change_submissions=True)
    table = SubmissionTable(
        SubmissionTable.base_queryset(event, user).none(),
        event=event,
        user=user,
        order_by=["-created", "bogus"],
    )

    form = table.export_form

    assert form.ordering == ["-created"]
    assert form.columns_form.sort_levels == [
        {"column": "created", "direction": "desc", "numeric": False}
    ]


def test_export_form_columns_fall_back_to_preferences_then_defaults(event):
    user = make_orga_user(event, can_change_submissions=True)
    default = TableExportForm(
        data=_data(), event=event, user=user, table_class=SubmissionTable
    )
    user.get_event_preferences(event).set(
        "tables.SubmissionTable.columns", ["state", "title", "actions"], commit=True
    )

    preferred = TableExportForm(
        data=_data(), event=event, user=user, table_class=SubmissionTable
    )

    assert default.columns == ["title", "speakers", "state", "is_featured"]
    assert preferred.columns == ["state", "title"]


@pytest.mark.parametrize(
    ("locales", "serializer", "locale", "options"),
    (
        (["en", "de"], "csv", None, None),
        (["en", "de"], "csv", "", None),
        (["en", "de"], "csv", "fr", None),
        (["en", "de"], "csv", "__all__", None),
        (
            ["en", "de"],
            "csv",
            "de",
            {"locale": "de", "delimiter": "", "list_delimiter": ""},
        ),
        (["en", "de"], "json", None, None),
        (["en", "de"], "json", "", None),
        (["en", "de"], "json", "fr", None),
        (["en", "de"], "json", "__all__", {"locale": "__all__"}),
        (["en", "de"], "json", "de", {"locale": "de"}),
        (["en"], "csv", None, {"delimiter": "", "list_delimiter": ""}),
        (["en"], "json", None, {}),
    ),
)
def test_export_form_requires_locale_for_chosen_format(
    locales, serializer, locale, options
):
    event = EventFactory(locales=locales)
    user = make_orga_user(event, can_change_submissions=True)
    field = f"{serializer}_locale"

    form = TableExportForm(
        data=_data(serializer=serializer, **{field: locale}),
        event=event,
        user=user,
        table_class=SubmissionTable,
    )

    assert ({"csv_locale", "json_locale"} <= set(form.fields)) is (len(locales) > 1)
    if options is None:
        assert not form.is_valid()
        assert list(form.errors) == [field]
    else:
        assert form.is_valid(), form.errors
        assert form.serializer_options == options


def test_export_form_reads_filter_widgets_when_no_querystring(event):
    user = make_orga_user(event, can_change_submissions=True)

    form = TableExportForm(
        data=_data(state=["accepted", "rejected"], q="needle", ordering=["title"]),
        event=event,
        user=user,
        table_class=SubmissionTable,
    )

    assert form.is_valid()
    assert form.filters == {"state": ["accepted", "rejected"], "q": ["needle"]}
    assert form.ordering == ["title"]
    assert form.filterset.is_set("state")


def test_export_form_saves_full_configuration(event):
    user = make_orga_user(event, can_change_submissions=True)
    form = TableExportForm(
        data=_data(
            name="Accepted talks",
            filters="state=accepted",
            columns=["title"],
            serializer="json",
        ),
        event=event,
        user=user,
        table_class=SubmissionTable,
        require_name=True,
    )

    assert form.is_valid(), form.errors
    export = form.save(commit=False)
    export.save()

    export = TableExport.objects.get(pk=export.pk)
    assert export.name == "Accepted talks"
    assert export.table == "SubmissionTable"
    assert export.columns == ["title"]
    assert export.filters == {"state": ["accepted"]}
    assert export.serializer == "json"
    assert export.serializer_options == {}


def test_export_form_requires_name_only_when_saving(event):
    user = make_orga_user(event, can_change_submissions=True)

    def toolbar_form(can_save=True, **data):
        return TableExportForm(
            data=_data(**data),
            event=event,
            user=user,
            table_class=SubmissionTable,
            can_save=can_save,
        )

    run_form = toolbar_form()
    checkbox_form = toolbar_form(save="1")
    unchecked_form = toolbar_form(save="false")
    unpermitted_form = toolbar_form(can_save=False, save="1")
    page_form = TableExportForm(
        data=_data(),
        event=event,
        user=user,
        table_class=SubmissionTable,
        require_name=True,
    )

    assert run_form.is_valid()
    assert not checkbox_form.is_valid()
    assert list(checkbox_form.errors) == ["name"]
    assert unchecked_form.is_valid()
    assert unchecked_form.cleaned_data["save"] is False
    assert unpermitted_form.is_valid()
    assert "save" not in unpermitted_form.fields
    assert not page_form.is_valid()
    assert list(page_form.errors) == ["name"]
    assert "save" not in page_form.fields


def test_export_form_initial_state_from_instance():
    event = EventFactory(locales=["en", "de"], locale="en")
    user = make_orga_user(event, can_change_submissions=True)
    export = TableExportFactory(
        event=event,
        columns=["state", "title"],
        ordering=["-created"],
        filters={"state": ["accepted"]},
        serializer="csv",
        serializer_options={"list_delimiter": "comma", "locale": "de"},
    )
    structured = TableExportFactory(event=event, serializer="json")
    outdated = TableExportFactory(event=event, serializer_options={"locale": "fr"})

    form = TableExportForm(
        instance=export, event=event, user=user, table_class=SubmissionTable
    )
    unsaved = TableExportForm(event=event, user=user, table_class=SubmissionTable)
    saved = TableExportForm(
        instance=structured, event=event, user=user, table_class=SubmissionTable
    )
    stale = TableExportForm(
        instance=outdated, event=event, user=user, table_class=SubmissionTable
    )

    assert [column["name"] for column in form.columns_form.shown_columns] == [
        "state",
        "title",
    ]
    assert form.columns_form.sort_levels == [
        {"column": "created", "direction": "desc", "numeric": False}
    ]
    assert form.fields["csv_locale"].initial == "de"
    assert form.fields["json_locale"].initial == "de"
    assert form.fields["csv_list_delimiter"].initial == "comma"
    assert form.filterset.is_set("state")
    assert unsaved.fields["csv_locale"].initial == "en"
    assert unsaved.fields["csv_locale"].required
    assert unsaved.fields["json_locale"].initial == "__all__"
    assert saved.fields["csv_locale"].initial == "en"
    assert saved.fields["json_locale"].initial == "__all__"
    assert stale.fields["csv_locale"].initial == "en"
    assert stale.fields["json_locale"].initial == "__all__"


def test_export_form_uses_given_table_for_the_picker(event):
    user = make_orga_user(event, can_change_submissions=True)
    table = SubmissionTable(
        SubmissionTable.base_queryset(event, user).none(), event=event, user=user
    )
    table.configure_export(["state", "title"])

    form = TableExportForm(
        event=event, user=user, table_class=SubmissionTable, table=table
    )
    without_user = TableExportForm(
        data=_data(filters="sort=state", ordering=["title"]),
        event=event,
        user=None,
        table_class=SubmissionTable,
        table=table,
    )

    assert form.table is table
    assert form.filterset is None
    assert [column["name"] for column in form.columns_form.shown_columns] == [
        "state",
        "title",
    ]
    assert "abstract" in {column["name"] for column in form.columns_form.hidden_columns}
    assert [identifier for identifier, _ in form.option_bound_fields] == ["csv", "csv"]
    assert without_user.preferences is None
    assert without_user.columns == ["state", "title"]
    assert without_user.ordering == ["title"]


def test_export_form_without_filters_or_serializer(event):
    user = make_orga_user(event, can_change_submissions=True)

    form = TableExportForm(
        data=_data(serializer="xlsx"), event=event, user=user, table_class=TrackTable
    )
    unsaved_user = TableExportForm(
        data=_data(), event=event, user=UserFactory.build(), table_class=TrackTable
    )

    assert form.is_valid() is False
    assert form.filterset is None
    assert form.filters == {}
    assert form.serializer_options == {}
    assert unsaved_user.preferences is None
    assert unsaved_user.columns == ["name", "proposals", "requires_access_code"]
