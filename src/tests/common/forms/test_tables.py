# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.forms.tables import (
    MAX_SORT_LEVELS,
    TablePreferencesForm,
    is_numeric_column,
)

pytestmark = pytest.mark.unit


class FakeColumn:
    def __init__(self, verbose_name, visible=True, orderable=True, attrs=None):
        self.verbose_name = verbose_name
        self.visible = visible
        self.orderable = orderable
        self.attrs = attrs


class FakeColumns:
    def __init__(self, mapping):
        self._mapping = mapping

    def items(self):
        return self._mapping.items()


class FakeTable:
    def __init__(
        self,
        columns,
        exempt_columns=(),
        current_ordering=None,
        default_columns=None,
        canonical_column_names=None,
    ):
        self.columns = FakeColumns(columns)
        self.exempt_columns = exempt_columns
        self.current_ordering = current_ordering or []
        self.canonical_column_names = canonical_column_names or list(columns)
        if default_columns is not None:
            self.default_columns = default_columns


def _make_table(**kwargs):
    columns = kwargs.pop(
        "columns",
        {
            "title": FakeColumn("Title"),
            "speaker": FakeColumn("Speaker"),
            "state": FakeColumn("State"),
        },
    )
    return FakeTable(columns=columns, **kwargs)


def _names(entries):
    return [entry["name"] for entry in entries]


def test_table_preferences_form_init_raises_without_table():
    with pytest.raises(ValueError, match="No table provided"):
        TablePreferencesForm()


def test_table_preferences_form_columns_split_by_visibility_keep_display_order():
    columns = {
        "title": FakeColumn("Title", visible=True),
        "notes": FakeColumn("Notes", visible=False),
        "speaker": FakeColumn("Speaker", visible=True),
        "abstract": FakeColumn("Abstract", visible=False),
    }
    table = _make_table(columns=columns)

    form = TablePreferencesForm(table=table)

    assert _names(form.shown_columns) == ["title", "speaker"]
    assert _names(form.hidden_columns) == ["notes", "abstract"]
    assert [column["order"] for column in form.hidden_columns] == [1, 3]


def test_table_preferences_form_hidden_columns_use_canonical_order():
    columns = {
        "speaker": FakeColumn("Speaker", visible=True),
        "abstract": FakeColumn("Abstract", visible=False),
        "title": FakeColumn("Title", visible=True),
        "notes": FakeColumn("Notes", visible=False),
    }
    table = _make_table(
        columns=columns,
        canonical_column_names=["title", "notes", "speaker", "abstract"],
    )

    form = TablePreferencesForm(table=table)

    assert _names(form.shown_columns) == ["speaker", "title"]
    assert [column["order"] for column in form.shown_columns] == [2, 0]
    assert _names(form.hidden_columns) == ["notes", "abstract"]
    assert [column["order"] for column in form.hidden_columns] == [1, 3]


def test_table_preferences_form_exempt_columns_excluded():
    columns = {
        "pk": FakeColumn("PK"),
        "title": FakeColumn("Title"),
        "actions": FakeColumn("Actions"),
    }
    table = _make_table(columns=columns, exempt_columns=("pk", "actions"))

    form = TablePreferencesForm(table=table)

    assert _names(form.shown_columns) == ["title"]
    assert _names(form.sort_choices) == ["title"]


@pytest.mark.parametrize(
    ("columns", "expected"),
    (
        pytest.param(
            {
                "title": FakeColumn("Title", orderable=True),
                "avatar": FakeColumn("Avatar", orderable=False),
            },
            [("title", False)],
            id="only_orderable_columns",
        ),
        pytest.param(
            {"title": FakeColumn("Zebra"), "speaker": FakeColumn("Anteater")},
            [("speaker", False), ("title", False)],
            id="sorted_by_label",
        ),
        pytest.param(
            {
                "title": FakeColumn("Title"),
                "score": FakeColumn("Score", attrs={"th": {"class": "numeric"}}),
            },
            [("score", True), ("title", False)],
            id="numeric_marked",
        ),
    ),
)
def test_table_preferences_form_sort_choices(columns, expected):
    table = _make_table(columns=columns)

    form = TablePreferencesForm(table=table)

    assert [
        (choice["name"], choice["numeric"]) for choice in form.sort_choices
    ] == expected


@pytest.mark.parametrize(
    ("attrs", "expected"),
    (
        (None, False),
        ({}, False),
        ({"td": {"class": "numeric"}}, False),
        ({"th": {"class": "numeric"}}, True),
        ({"th": {"class": "numeric text-center"}}, True),
    ),
)
def test_is_numeric_column(attrs, expected):
    assert is_numeric_column(FakeColumn("Score", attrs=attrs)) is expected


@pytest.mark.parametrize(
    ("current_ordering", "expected"),
    (
        ([], []),
        (
            [{"column": "title", "direction": "asc"}],
            [{"column": "title", "direction": "asc", "numeric": False}],
        ),
        (
            [
                {"column": "title", "direction": "asc"},
                {"column": "state", "direction": "desc"},
            ],
            [
                {"column": "title", "direction": "asc", "numeric": False},
                {"column": "state", "direction": "desc", "numeric": False},
            ],
        ),
    ),
    ids=["no_ordering", "single_ordering", "two_orderings"],
)
def test_table_preferences_form_sort_levels(current_ordering, expected):
    table = _make_table(current_ordering=current_ordering)

    form = TablePreferencesForm(table=table)

    assert form.sort_levels == expected


def test_table_preferences_form_sort_levels_skip_unsortable_columns():
    columns = {
        "title": FakeColumn("Title"),
        "avatar": FakeColumn("Avatar", orderable=False),
    }
    table = _make_table(
        columns=columns,
        current_ordering=[
            {"column": "avatar", "direction": "asc"},
            {"column": "title", "direction": "desc"},
        ],
    )

    form = TablePreferencesForm(table=table)

    assert form.sort_levels == [
        {"column": "title", "direction": "desc", "numeric": False}
    ]


def test_table_preferences_form_sort_levels_capped():
    names = [f"col{index}" for index in range(MAX_SORT_LEVELS + 1)]
    columns = {name: FakeColumn(name.title()) for name in names}
    table = _make_table(
        columns=columns,
        current_ordering=[{"column": name, "direction": "asc"} for name in names],
    )

    form = TablePreferencesForm(table=table)

    assert [level["column"] for level in form.sort_levels] == names[:MAX_SORT_LEVELS]


@pytest.mark.parametrize(
    ("default_columns", "expected", "expected_json"),
    (
        pytest.param(
            ("title", "notes", "gone"),
            ["title", "notes"],
            '["title", "notes"]',
            id="from_table",
        ),
        pytest.param(None, ["title"], '["title"]', id="fall_back_to_shown"),
    ),
)
def test_table_preferences_form_default_columns(
    default_columns, expected, expected_json
):
    columns = {
        "title": FakeColumn("Title"),
        "notes": FakeColumn("Notes", visible=False),
    }
    table = _make_table(columns=columns, default_columns=default_columns)

    form = TablePreferencesForm(table=table)

    assert form.default_columns == expected
    assert form.default_columns_json == expected_json
