import pytest

from pretalx.common.forms.tables import DIRECTION_CHOICES, TablePreferencesForm

pytestmark = pytest.mark.unit


# TablePreferencesForm uses duck-typed table objects with pretalx-specific
# attributes (exempt_columns, current_ordering) on top of the django_tables2
# Column interface. Constructing a real django_tables2 Table with these custom
# attributes would require a model, queryset, and view context — far more setup
# than the form logic we're testing. These lightweight stubs expose just the
# interface the form reads from.


class FakeColumn:
    def __init__(self, verbose_name, visible=True, orderable=True):
        self.verbose_name = verbose_name
        self.visible = visible
        self.orderable = orderable


class FakeColumns:
    """Minimal dict-like wrapper that also supports attribute access for BoundColumn-like behaviour."""

    def __init__(self, mapping):
        self._mapping = mapping

    def items(self):
        return self._mapping.items()

    def __getitem__(self, key):
        return self._mapping[key]


class FakeTable:
    def __init__(self, columns, exempt_columns=(), current_ordering=None):
        self.columns = FakeColumns(columns)
        self.exempt_columns = exempt_columns
        self.current_ordering = current_ordering or []


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


def test_table_preferences_form_init_raises_without_table():
    with pytest.raises(ValueError, match="No table provided"):
        TablePreferencesForm()


def test_table_preferences_form_visible_columns_as_selected():
    table = _make_table()

    form = TablePreferencesForm(table=table)

    column_names = {name for name, _ in form.fields["columns"].choices}
    assert column_names == {"title", "speaker", "state"}


def test_table_preferences_form_hidden_columns_as_available():
    columns = {
        "title": FakeColumn("Title", visible=True),
        "notes": FakeColumn("Notes", visible=False),
    }
    table = _make_table(columns=columns)

    form = TablePreferencesForm(table=table)

    available_names = {name for name, _ in form.fields["available_columns"].choices}
    assert available_names == {"notes"}
    selected_names = {name for name, _ in form.fields["columns"].choices}
    assert selected_names == {"title"}


def test_table_preferences_form_exempt_columns_excluded():
    columns = {
        "pk": FakeColumn("PK"),
        "title": FakeColumn("Title"),
        "actions": FakeColumn("Actions"),
    }
    table = _make_table(columns=columns, exempt_columns=("pk", "actions"))

    form = TablePreferencesForm(table=table)

    all_column_names = {name for name, _ in form.fields["columns"].choices} | {
        name for name, _ in form.fields["available_columns"].choices
    }
    assert all_column_names == {"title"}


def test_table_preferences_form_sort_choices_include_only_orderable_columns():
    columns = {
        "title": FakeColumn("Title", orderable=True),
        "avatar": FakeColumn("Avatar", orderable=False),
    }
    table = _make_table(columns=columns)

    form = TablePreferencesForm(table=table)

    assert form.fields["sort_column_1"].choices == [
        ("", "---------"),
        ("title", "Title"),
    ]


def test_table_preferences_form_sort_choices_exclude_exempt_columns():
    columns = {
        "pk": FakeColumn("PK", orderable=True),
        "title": FakeColumn("Title", orderable=True),
    }
    table = _make_table(columns=columns, exempt_columns=("pk",))

    form = TablePreferencesForm(table=table)

    assert form.fields["sort_column_1"].choices == [
        ("", "---------"),
        ("title", "Title"),
    ]


def test_table_preferences_form_both_sort_column_fields_share_choices():
    table = _make_table()

    form = TablePreferencesForm(table=table)

    assert form.fields["sort_column_1"].choices == form.fields["sort_column_2"].choices


def test_table_preferences_form_direction_fields_use_direction_choices():
    form = TablePreferencesForm(table=_make_table())

    assert form.fields["sort_direction_1"].choices == DIRECTION_CHOICES
    assert form.fields["sort_direction_2"].choices == DIRECTION_CHOICES


@pytest.mark.parametrize(
    ("current_ordering", "expected"),
    (
        ([], {"col1": None, "dir1": None, "col2": None, "dir2": None}),
        (
            [{"column": "title", "direction": "asc"}],
            {"col1": "title", "dir1": "asc", "col2": None, "dir2": None},
        ),
        (
            [
                {"column": "title", "direction": "asc"},
                {"column": "state", "direction": "desc"},
            ],
            {"col1": "title", "dir1": "asc", "col2": "state", "dir2": "desc"},
        ),
    ),
    ids=["no_ordering", "single_ordering", "two_orderings"],
)
def test_table_preferences_form_ordering_sets_sort_initials(current_ordering, expected):
    table = _make_table(current_ordering=current_ordering)

    form = TablePreferencesForm(table=table)

    assert form.fields["sort_column_1"].initial == expected["col1"]
    assert form.fields["sort_direction_1"].initial == expected["dir1"]
    assert form.fields["sort_column_2"].initial == expected["col2"]
    assert form.fields["sort_direction_2"].initial == expected["dir2"]


def test_table_preferences_form_columns_initial_empty():
    table = _make_table()

    form = TablePreferencesForm(table=table)

    assert form.fields["columns"].initial == []


def test_table_preferences_form_available_columns_sorted():
    columns = {
        "title": FakeColumn("Title", visible=False),
        "abstract": FakeColumn("Abstract", visible=False),
        "speaker": FakeColumn("Speaker", visible=False),
    }
    table = _make_table(columns=columns)

    form = TablePreferencesForm(table=table)

    available_choices = form.fields["available_columns"].choices
    names = [name for name, _ in available_choices]
    assert names == sorted(names)
