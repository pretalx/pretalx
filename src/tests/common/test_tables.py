# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from datetime import UTC, datetime
from types import SimpleNamespace

import django_tables2 as tables
import pytest
from django.contrib.auth.models import AnonymousUser
from django.db.models.functions import Lower
from django.template import Context
from django.test import RequestFactory
from django.utils.safestring import SafeString
from django_scopes import scopes_disabled
from django_tables2.utils import OrderByTuple

from pretalx.common.tables import (
    ActionsColumn,
    BooleanColumn,
    DateTimeColumn,
    IndependentScoreColumn,
    PretalxTable,
    QuestionColumn,
    QuestionColumnMixin,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
    UnsortableMixin,
    get_icon,
)
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Submission
from tests.factories import (
    AnswerFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


class SimpleTable(PretalxTable):
    title = tables.Column()
    code = tables.Column()

    class Meta:
        model = Submission
        fields = ("title", "code")


class SimpleTableWithHidden(PretalxTable):
    title = tables.Column()
    code = tables.Column()
    internal = tables.Column(visible=False)

    class Meta:
        model = Submission
        fields = ("title", "code", "internal")


class SortableTestTable(PretalxTable):
    title = SortableColumn(order_by=Lower("title"))
    code = tables.Column()

    class Meta:
        model = Submission
        fields = ("title", "code")


class UnsortableTestTable(UnsortableMixin, PretalxTable):
    title = tables.Column()

    class Meta:
        model = Submission
        fields = ("title",)


def test_get_icon_returns_safe_html():
    result = get_icon("edit")

    assert isinstance(result, SafeString)
    assert result == '<i class="fa fa-edit"></i>'


@pytest.mark.django_db
def test_pretalx_table_stores_constructor_args(event):
    user = UserFactory()

    table = SimpleTable(
        [],
        event=event,
        user=user,
        has_update_permission=True,
        has_delete_permission=True,
    )

    assert table.event is event
    assert table.user is user
    assert table.has_update_permission is True
    assert table.has_delete_permission is True


@pytest.mark.django_db
def test_pretalx_table_name_returns_class_name():
    table = SimpleTable([])

    assert table.name == "SimpleTable"


@pytest.mark.django_db
def test_pretalx_table_selected_columns_returns_visible():
    table = SimpleTableWithHidden([])

    selected = table.selected_columns

    names = {name for name, _ in selected}
    assert names == {"title", "code"}


@pytest.mark.django_db
def test_pretalx_table_available_columns_returns_hidden():
    table = SimpleTableWithHidden([])

    available = table.available_columns

    names = [name for name, _ in available]
    assert names == ["internal"]


@pytest.mark.django_db
def test_pretalx_table_exempt_columns_excluded_from_selected():
    """pk and actions are exempt — they never appear in selected/available."""

    class TableWithPk(PretalxTable):
        pk = tables.Column()
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("pk", "title")

    table = TableWithPk([])
    selected = table.selected_columns

    names = {name for name, _ in selected}
    assert names == {"title"}


@pytest.mark.django_db
def test_pretalx_table_current_ordering_empty_when_no_order():
    table = SimpleTable([])

    assert table.current_ordering == []


@pytest.mark.django_db
def test_pretalx_table_current_ordering_returns_asc_desc():
    table = SimpleTable([], order_by="title,-code")

    ordering = table.current_ordering

    assert ordering == [
        {"column": "title", "direction": "asc"},
        {"column": "code", "direction": "desc"},
    ]


@pytest.mark.django_db
def test_pretalx_table_set_columns_shows_selected_and_hides_rest():
    table = SimpleTableWithHidden([])

    table._set_columns(["title", "internal"])

    visible = {name for name, col in table.columns.items() if col.visible}
    assert visible == {"title", "internal"}


@pytest.mark.django_db
def test_pretalx_table_set_columns_ignores_invalid_names():
    table = SimpleTable([])

    table._set_columns(["title", "nonexistent"])

    visible = {name for name, col in table.columns.items() if col.visible}
    assert visible == {"title"}


@pytest.mark.django_db
def test_pretalx_table_set_columns_puts_pk_first_and_actions_last():
    class TableWithPkAndActions(PretalxTable):
        pk = tables.Column()
        title = tables.Column()
        actions = tables.Column()

        class Meta:
            model = Submission
            fields = ("pk", "title", "actions")

    table = TableWithPkAndActions([])
    table._set_columns(["title"])

    assert table.sequence[0] == "pk"
    assert table.sequence[-1] == "actions"


@pytest.mark.parametrize(
    ("ordering", "expected"),
    (
        pytest.param(["title", "-code"], ["title", "-code"], id="valid_columns"),
        pytest.param(["title", "-title"], ["title"], id="removes_duplicates"),
        pytest.param(["nonexistent"], None, id="all_invalid"),
        pytest.param([], [], id="empty"),
    ),
)
@pytest.mark.django_db
def test_pretalx_table_validate_ordering(ordering, expected):
    table = SimpleTable([])

    result = table._validate_ordering(ordering)

    assert result == expected


@pytest.mark.parametrize(
    ("new", "saved", "expected"),
    (
        pytest.param(["title"], [], ["title"], id="no_saved"),
        pytest.param([], ["title", "-code"], [], id="no_new"),
        pytest.param(
            ["-code"], ["title", "-code"], ["-code", "-code"], id="preserves_secondary"
        ),
        pytest.param(
            ["title", "code"],
            ["code", "-title"],
            ["title", "code"],
            id="two_new_ignores_saved",
        ),
        pytest.param(["title"], ["-code"], ["title"], id="single_saved"),
    ),
)
@pytest.mark.django_db
def test_pretalx_table_merge_ordering(new, saved, expected):
    table = SimpleTable([])

    result = table._merge_ordering(new, saved)

    assert result == expected


@pytest.mark.parametrize(
    ("field_name", "expected"),
    (
        pytest.param("title", True, id="valid_model_field"),
        pytest.param("nonexistent", False, id="unknown_field"),
    ),
)
@pytest.mark.django_db
def test_pretalx_table_is_model_field(field_name, expected):
    table = SimpleTable([])

    assert table._is_model_field(field_name) is expected


def test_pretalx_table_is_model_field_without_meta_model():
    class NoMetaTable(PretalxTable):
        title = tables.Column()

    table = NoMetaTable([])

    assert table._is_model_field("title") is False


@pytest.mark.parametrize(
    ("ordering", "expected_titles"),
    (
        pytest.param(["title"], ["Alpha", "Bravo"], id="ascending"),
        pytest.param(["-title"], ["Bravo", "Alpha"], id="descending"),
    ),
)
@pytest.mark.django_db
def test_pretalx_table_apply_ordering_by_model_field(event, ordering, expected_titles):
    with scopes_disabled():
        SubmissionFactory(event=event, title="Alpha")
        SubmissionFactory(event=event, title="Bravo")
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)

    ordered = table._apply_ordering(qs, ordering)
    titles = list(ordered.values_list("title", flat=True))

    assert titles == expected_titles


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_empty_returns_queryset(event):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)

    result = table._apply_ordering(qs, [])

    assert result is qs


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_skips_unknown_columns(event):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)

    result = table._apply_ordering(qs, ["nonexistent"])

    assert list(result) == list(qs)


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_with_function_order_column(event):
    with scopes_disabled():
        SubmissionFactory(event=event, title="Bravo")
        SubmissionFactory(event=event, title="alpha")
        qs = Submission.objects.filter(event=event)

    table = SortableTestTable(qs, event=event)

    ordered = table._apply_ordering(qs, ["title"])
    titles = list(ordered.values_list("title", flat=True))

    assert titles == ["alpha", "Bravo"]


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_with_bound_column_order_by(event):
    """Columns with explicit order_by accessors that are not function-based."""

    class AccessorTable(PretalxTable):
        code = tables.Column(order_by=("code",))

        class Meta:
            model = Submission
            fields = ("code",)

    with scopes_disabled():
        s1 = SubmissionFactory(event=event)
        s2 = SubmissionFactory(event=event)
        qs = Submission.objects.filter(event=event)

    table = AccessorTable(qs, event=event)
    ordered = table._apply_ordering(qs, ["code"])
    codes = list(ordered.values_list("code", flat=True))

    assert codes == sorted([s1.code, s2.code])


@pytest.mark.django_db
def test_pretalx_table_get_sortable_column_names():
    table = SimpleTable([])

    sortable = table._get_sortable_column_names()

    assert sortable == {"title", "code"}


@pytest.mark.django_db
def test_pretalx_table_configuration_form_none_when_no_hidden_or_defaults():
    table = SimpleTable([])

    assert table.configuration_form is None


@pytest.mark.django_db
def test_pretalx_table_configuration_form_returned_when_hidden_columns():
    table = SimpleTableWithHidden([])

    form = table.configuration_form

    assert form is not None
    assert form.table is table


@pytest.mark.django_db
def test_pretalx_table_configuration_form_returned_when_default_columns():
    class DefaultColumnsTable(PretalxTable):
        title = tables.Column()
        code = tables.Column()
        default_columns = ["title"]

        class Meta:
            model = Submission
            fields = ("title", "code")

    table = DefaultColumnsTable([])

    form = table.configuration_form

    assert form is not None


@pytest.mark.django_db
def test_pretalx_table_configure_with_anonymous_user(event):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/")
    request.user = AnonymousUser()

    page_size = table.configure(request)

    assert page_size is None


@pytest.mark.django_db
def test_pretalx_table_configure_applies_saved_columns(event):
    user = UserFactory()
    with scopes_disabled():
        prefs = user.get_event_preferences(event)
        prefs.set(
            "tables.SimpleTableWithHidden.columns", ["title", "internal"], commit=True
        )
        qs = Submission.objects.filter(event=event)

    table = SimpleTableWithHidden(qs, event=event)
    request = RequestFactory().get("/")
    request.user = user

    table.configure(request)

    visible = {name for name, col in table.columns.items() if col.visible}
    assert visible == {"title", "internal"}


@pytest.mark.django_db
def test_pretalx_table_configure_applies_ordering_from_query(event):
    user = UserFactory()
    with scopes_disabled():
        SubmissionFactory(event=event, title="Bravo")
        SubmissionFactory(event=event, title="Alpha")
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/?sort=title")
    request.GET = request.GET.copy()
    request.GET.setlist("sort", ["title"])
    request.user = user

    table.configure(request)

    assert table._ordering_applied is True
    titles = list(table.data.data.values_list("title", flat=True))
    assert titles == ["Alpha", "Bravo"]


@pytest.mark.django_db
def test_pretalx_table_configure_saves_ordering_to_preferences(event):
    user = UserFactory()
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/?sort=title")
    request.GET = request.GET.copy()
    request.GET.setlist("sort", ["title"])
    request.user = user

    table.configure(request)

    with scopes_disabled():
        prefs = user.get_event_preferences(event)
        saved = prefs.get("tables.SimpleTable.ordering")
    assert saved == ["title"]


@pytest.mark.django_db
def test_pretalx_table_configure_uses_saved_ordering_when_no_query(event):
    user = UserFactory()
    with scopes_disabled():
        prefs = user.get_event_preferences(event)
        prefs.set("tables.SimpleTable.ordering", ["-title"], commit=True)
        SubmissionFactory(event=event, title="Alpha")
        SubmissionFactory(event=event, title="Bravo")
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/")
    request.user = user

    table.configure(request)

    titles = list(table.data.data.values_list("title", flat=True))
    assert titles == ["Bravo", "Alpha"]


@pytest.mark.django_db
def test_pretalx_table_configure_returns_page_size(event):
    user = UserFactory()
    with scopes_disabled():
        prefs = user.get_event_preferences(event)
        prefs.set("tables.SimpleTable.page_size", 25, commit=True)
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/")
    request.user = user

    page_size = table.configure(request)

    assert page_size == 25


@pytest.mark.django_db
def test_pretalx_table_configure_falls_back_to_meta_fields(event):
    """When no preferences or default_columns, uses Meta.fields."""
    user = UserFactory()
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/")
    request.user = user

    table.configure(request)

    visible = {name for name, col in table.columns.items() if col.visible}
    assert visible == {"title", "code"}


@pytest.mark.django_db
def test_pretalx_table_order_by_setter_after_ordering_applied_updates_display_only(
    event,
):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    table._ordering_applied = True
    table._order_by = ("title", "-code")

    table.order_by = "code"

    # Display should show code with secondary sort preserved
    assert "code" in [str(o) for o in table._order_by]


@pytest.mark.django_db
def test_pretalx_table_order_by_setter_before_ordering_applied_uses_parent(event):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)

    table.order_by = "title"

    assert str(table.order_by[0]) == "title"


@pytest.mark.django_db
def test_unsortable_mixin_disables_ordering():
    table = UnsortableTestTable([])

    assert table.orderable is False
    assert not table.order_by


@pytest.mark.django_db
def test_sortable_column_stores_function_lookup():
    col = SortableColumn(order_by=Lower("title"))

    assert "title" in col.order_function_lookup
    assert isinstance(col.order_function_lookup["title"], Lower)


@pytest.mark.django_db
def test_sortable_column_with_string_order_by():
    col = SortableColumn(order_by="title")

    assert col.order_function_lookup == {}


@pytest.mark.parametrize(
    ("is_descending", "expected_titles"),
    (
        pytest.param(False, ["Alpha", "bravo"], id="ascending"),
        pytest.param(True, ["bravo", "Alpha"], id="descending"),
    ),
)
@pytest.mark.django_db
def test_sortable_column_order(event, is_descending, expected_titles):
    with scopes_disabled():
        SubmissionFactory(event=event, title="bravo")
        SubmissionFactory(event=event, title="Alpha")
        qs = Submission.objects.filter(event=event)

    col = SortableColumn(order_by=Lower("title"))
    ordered_qs, modified = col.order(qs, is_descending=is_descending)

    assert modified is True
    titles = list(ordered_qs.values_list("title", flat=True))
    assert titles == expected_titles


@pytest.mark.django_db
def test_function_order_mixin_no_lookup_returns_unmodified(event):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    col = SortableColumn(order_by="title")
    result_qs, modified = col.order(qs, is_descending=False)

    assert modified is False


@pytest.mark.django_db
def test_function_order_mixin_apply_function_ordering_returns_annotated_qs(event):
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    col = SortableColumn(order_by=Lower("title"))
    result_qs, order_keys = col.apply_function_ordering(qs, descending=False)

    assert len(order_keys) == 1
    assert "_sort_title" in order_keys[0]


@pytest.mark.django_db
def test_sortable_template_column_inherits_function_order():
    col = SortableTemplateColumn(template_code="{{ value }}", order_by=Lower("title"))

    assert "title" in col.order_function_lookup


@pytest.mark.django_db
def test_template_column_renders_template_code(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(template_code="{{ record.title }}")

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        sub = SubmissionFactory(event=event, title="My Talk")
        qs = Submission.objects.filter(pk=sub.pk)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    # Force rendering by iterating rows
    rows = list(table.rows)
    rendered = rows[0].get_cell("title")

    assert "My Talk" in rendered


@pytest.mark.django_db
def test_template_column_returns_placeholder_for_empty(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(template_code="{{ nothing }}")

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        SubmissionFactory(event=event)
        qs = Submission.objects.filter(event=event)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    rows = list(table.rows)
    rendered = rows[0].get_cell("title")

    assert "&mdash;" in str(rendered)


@pytest.mark.django_db
def test_template_column_custom_context_object_name(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(
            template_code="{{ submission.title }}", context_object_name="submission"
        )

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        sub = SubmissionFactory(event=event, title="Custom Context")
        qs = Submission.objects.filter(pk=sub.pk)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    rows = list(table.rows)
    rendered = rows[0].get_cell("title")

    assert "Custom Context" in rendered


@pytest.mark.django_db
def test_template_column_callable_template_context(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(
            template_code="{{ extra_info }}",
            template_context={
                "extra_info": lambda record, table: f"info-{record.code}"
            },
        )

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        sub = SubmissionFactory(event=event)
        qs = Submission.objects.filter(pk=sub.pk)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    rows = list(table.rows)
    rendered = rows[0].get_cell("title")

    assert f"info-{sub.code}" in rendered


@pytest.mark.django_db
def test_template_column_static_template_context(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(
            template_code="{{ greeting }}", template_context={"greeting": "hello"}
        )

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        SubmissionFactory(event=event)
        qs = Submission.objects.filter(event=event)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    rows = list(table.rows)
    rendered = rows[0].get_cell("title")

    assert "hello" in rendered


@pytest.mark.django_db
def test_template_column_value_returns_empty_for_placeholder(event):
    """TemplateColumn.value() returns "" when result matches placeholder."""

    class TplTable(PretalxTable):
        title = TemplateColumn(template_code="{{ nothing }}")

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        SubmissionFactory(event=event)
        qs = Submission.objects.filter(event=event)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    rows = list(table.rows)
    # value() is used for CSV export; it returns "" for placeholder content
    value = rows[0].get_cell_value("title")
    assert value == ""


@pytest.mark.django_db
def test_template_column_value_returns_rendered_content(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(template_code="{{ record.title }}")

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        SubmissionFactory(event=event, title="Rendered Value")
        qs = Submission.objects.filter(event=event)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    table.request = request

    rows = list(table.rows)
    value = rows[0].get_cell_value("title")
    assert "Rendered Value" in value


@pytest.mark.django_db
def test_template_column_with_template_name(event):
    """TemplateColumn can render from a template file path."""

    class TplTable(PretalxTable):
        answer_col = TemplateColumn(template_name="common/question_answer.html")

        class Meta:
            model = Submission
            fields = ()
            sequence = ("answer_col",)

    with scopes_disabled():
        sub = SubmissionFactory(event=event)
        qs = Submission.objects.filter(pk=sub.pk)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request
    # Provide context with answer = None so template renders "No response"
    table.context = Context({"answer": None})

    rows = list(table.rows)
    rendered = str(rows[0].get_cell("answer_col"))

    assert "No response" in rendered


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        pytest.param(True, "text-success", id="true"),
        pytest.param(False, "text-danger", id="false"),
        pytest.param(None, "text-muted", id="none"),
    ),
)
def test_boolean_column_render(value, expected):
    col = BooleanColumn()

    result = col.render(value)

    assert isinstance(result, SafeString)
    assert expected in str(result)


@pytest.mark.django_db
def test_datetime_column_render_with_event_timezone(event):

    col = DateTimeColumn()
    dt = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    table = SimpleNamespace(event=event)

    result = col.render(record=None, table=table, value=dt, bound_column=None)

    assert "2024-06-15" in result
    assert ":" in result


@pytest.mark.django_db
def test_datetime_column_render_without_value():
    col = DateTimeColumn()

    result = col.render(record=None, table=None, value=None, bound_column=None)

    assert "&mdash;" in str(result)


@pytest.mark.django_db
def test_datetime_column_render_without_event():

    col = DateTimeColumn()
    dt = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    table = SimpleNamespace(event=None)

    result = col.render(record=None, table=table, value=dt, bound_column=None)

    assert "2024-06-15" in result


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        pytest.param(
            datetime(2024, 6, 15, 14, 30, tzinfo=UTC),
            "2024-06-15T14:30:00+00:00",
            id="with_value",
        ),
        pytest.param(None, None, id="none"),
    ),
)
def test_datetime_column_value(value, expected):
    col = DateTimeColumn()

    result = col.value(value)

    assert result == expected


def test_actions_column_header_is_empty():
    col = ActionsColumn(actions={"edit": {}})

    assert col.header() == ""


def test_actions_column_orderable_is_false():
    col = ActionsColumn(actions={"edit": {}})

    assert col.orderable is False


def test_actions_column_merges_with_defaults():
    col = ActionsColumn(actions={"edit": {"url": "custom_urls.edit"}})

    assert col.actions["edit"]["url"] == "custom_urls.edit"
    assert col.actions["edit"]["icon"] == "edit"  # from default


def test_actions_column_custom_action():
    col = ActionsColumn(
        actions={"custom": {"icon": "star", "color": "warning", "url": "urls.custom"}}
    )

    assert col.actions["custom"]["icon"] == "star"
    assert col.actions["custom"]["color"] == "warning"


def test_actions_column_render_empty_when_no_pk():
    col = ActionsColumn(actions={"edit": {}})
    record = SimpleNamespace(pk=None)

    result = col.render(record=record, table=SimpleNamespace(context={}))

    assert result == ""


def test_actions_column_render_empty_when_no_actions():
    col = ActionsColumn(actions={})
    record = SimpleNamespace(pk=1)

    result = col.render(record=record, table=SimpleNamespace(context={}))

    assert result == ""


def test_actions_column_render_button_when_no_url():
    """Actions without a URL render as <button> elements."""
    col = ActionsColumn(actions={"sort": {}})
    record = SimpleNamespace(pk=1)
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert "<button" in str(result)
    assert "dragsort-button" in str(result)


def test_actions_column_render_link_with_dotted_url():
    """Actions with a dotted string URL resolve through record attributes."""
    col = ActionsColumn(actions={"edit": {"url": "urls.edit"}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/events/test/edit/"))
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert '<a href="/events/test/edit/"' in str(result)
    assert "fa-edit" in str(result)


def test_actions_column_render_link_with_callable_url():
    col = ActionsColumn(
        actions={
            "view": {
                "icon": "eye",
                "color": "info",
                "url": lambda record: f"/view/{record.pk}/",
                "permission": "update",
            }
        }
    )
    record = SimpleNamespace(pk=42)
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert '<a href="/view/42/"' in str(result)


def test_actions_column_render_with_next_url():
    col = ActionsColumn(actions={"delete": {}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(delete="/delete/"))
    request = SimpleNamespace(
        user=SimpleNamespace(has_perm=lambda perm, obj: True),
        get_full_path=lambda: "/current/?page=2",
    )
    table = SimpleNamespace(context={"request": request}, has_delete_permission=True)

    result = col.render(record=record, table=table)

    assert "next=" in str(result)
    assert "/delete/" in str(result)


def test_actions_column_skips_action_when_condition_false():
    col = ActionsColumn(actions={"edit": {"condition": lambda record: False}})
    record = SimpleNamespace(pk=1)
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert "fa-edit" not in str(result)


def test_actions_column_shows_action_when_condition_true():
    col = ActionsColumn(actions={"edit": {"condition": lambda record: True}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/"))
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert "fa-edit" in str(result)


def test_actions_column_permission_check_via_table_attr():
    """When table has has_<permission>_permission attribute, use that."""
    col = ActionsColumn(actions={"edit": {}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/"))
    request = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm, obj: False))
    table = SimpleNamespace(context={"request": request}, has_update_permission=False)

    result = col.render(record=record, table=table)

    assert "fa-edit" not in str(result)


def test_actions_column_permission_check_via_user_has_perm():
    """When table doesn't have the permission attr, fall back to user.has_perm."""
    col = ActionsColumn(actions={"edit": {}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/"))
    request = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm, obj: True))
    table = SimpleNamespace(context={"request": request})

    result = col.render(record=record, table=table)

    assert "fa-edit" in str(result)


def test_actions_column_render_with_label():
    col = ActionsColumn(
        actions={
            "custom": {"color": "info", "label": "Click me", "permission": "update"}
        }
    )
    record = SimpleNamespace(pk=1)
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert "Click me" in str(result)


def test_actions_column_render_with_callable_extra_attrs():
    col = ActionsColumn(
        actions={"copy": {"extra_attrs": lambda record: f'data-id="{record.pk}"'}}
    )
    record = SimpleNamespace(pk=99)
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert 'data-id="99"' in str(result)


def test_actions_column_render_callable_dotted_url():
    """Dotted URL path where intermediate parts are callables."""
    col = ActionsColumn(
        actions={"edit": {"url": "get_urls.edit", "permission": "update"}}
    )
    record = SimpleNamespace(pk=1, get_urls=lambda: SimpleNamespace(edit="/resolved/"))
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert "/resolved/" in str(result)


def test_actions_column_no_user_no_request_renders_all():
    """When there's no request/user, permission checks are skipped."""
    col = ActionsColumn(actions={"edit": {}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/"))
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert "fa-edit" in str(result)


def test_independent_score_column_stores_category():
    category = SimpleNamespace(pk=5, name="Relevance")
    col = IndependentScoreColumn(category=category)

    assert col.category is category
    assert col.orderable is False


def test_independent_score_column_render_with_score():
    category = SimpleNamespace(pk=5)
    col = IndependentScoreColumn(category=category)
    record = SimpleNamespace(pk=1)
    table = SimpleNamespace(get_independent_score=lambda record, pk: 4.2)

    result = col.render(record=record, table=table)

    assert result == 4.2


def test_independent_score_column_render_none_returns_placeholder():
    category = SimpleNamespace(pk=5)
    col = IndependentScoreColumn(category=category)
    record = SimpleNamespace(pk=1)
    table = SimpleNamespace(get_independent_score=lambda record, pk: None)

    result = col.render(record=record, table=table)

    assert "&mdash;" in str(result)


@pytest.mark.django_db
def test_question_column_mixin_submission_model():
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    table = TestTable([])

    assert table._question_model == "submission"


@pytest.mark.django_db
def test_question_column_mixin_speaker_model():

    class TestTable(QuestionColumnMixin, PretalxTable):
        name = tables.Column()

        class Meta:
            model = SpeakerProfile
            fields = ("name",)

    table = TestTable([])

    assert table._question_model == "speaker"


@pytest.mark.django_db
def test_question_column_mixin_get_question_columns(event):
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        q1 = QuestionFactory(event=event, question="Favorite color")
        q2 = QuestionFactory(event=event, question="T-shirt size")

    table = TestTable([])
    table.short_questions = [q1, q2]

    columns = table._get_question_columns()

    assert len(columns) == 2
    assert columns[0][0] == f"question_{q1.id}"
    assert columns[1][0] == f"question_{q2.id}"
    assert isinstance(columns[0][1], QuestionColumn)


@pytest.mark.django_db
def test_question_column_mixin_get_question_columns_empty():
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    table = TestTable([])
    table.short_questions = None

    assert table._get_question_columns() == []


@pytest.mark.django_db
def test_question_column_mixin_get_answer_for_question(event):
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event)
        submission = SubmissionFactory(event=event)
        answer = AnswerFactory(question=question, submission=submission, answer="42")
        qs = Submission.objects.filter(pk=submission.pk)

    table = TestTable(qs)
    table.short_questions = [question]
    table._question_model = "submission"

    with scopes_disabled():
        result = table.get_answer_for_question(submission, question.id)

    assert result.pk == answer.pk
    assert result.answer == "42"


@pytest.mark.django_db
def test_question_column_mixin_get_answer_no_questions():
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    table = TestTable([])
    table.short_questions = None

    result = table.get_answer_for_question(SimpleNamespace(pk=1), 999)

    assert result is None


@pytest.mark.django_db
def test_question_column_mixin_answer_cache_is_loaded_once(event):
    """The answer cache is loaded on first access and reused."""

    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event)
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        a1 = AnswerFactory(question=question, submission=sub1, answer="First")
        a2 = AnswerFactory(question=question, submission=sub2, answer="Second")
        qs = Submission.objects.filter(pk__in=[sub1.pk, sub2.pk])

    table = TestTable(qs)
    table.short_questions = [question]
    table._question_model = "submission"

    with scopes_disabled():
        # First access loads cache
        result1 = table.get_answer_for_question(sub1, question.id)
        # Second access uses cache
        result2 = table.get_answer_for_question(sub2, question.id)

    assert result1.pk == a1.pk
    assert result2.pk == a2.pk
    assert hasattr(table, "_answers_cache")


@pytest.mark.django_db
def test_question_column_mixin_speaker_answer(event):

    class SpeakerTestTable(QuestionColumnMixin, PretalxTable):
        name = tables.Column()

        class Meta:
            model = SpeakerProfile
            fields = ("name",)

    with scopes_disabled():
        question = QuestionFactory(event=event, target="speaker")
        speaker = SpeakerFactory(event=event)
        answer = AnswerFactory(
            question=question, submission=None, speaker=speaker, answer="Yes"
        )
        qs = SpeakerProfile.objects.filter(pk=speaker.pk)

    table = SpeakerTestTable(qs)
    table.short_questions = [question]
    table._question_model = "speaker"

    with scopes_disabled():
        result = table.get_answer_for_question(speaker, question.id)

    assert result.pk == answer.pk


@pytest.mark.django_db
def test_question_column_mixin_load_answers_empty_records(event):
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event)

    table = TestTable([])
    table.short_questions = [question]
    table._question_model = "submission"

    with scopes_disabled():
        table._load_all_answers()

    assert table._answers_cache == {}


@pytest.mark.django_db
def test_question_column_stores_question(event):
    with scopes_disabled():
        question = QuestionFactory(event=event)

    col = QuestionColumn(question=question)

    assert col.question is question
    assert col.orderable is True


@pytest.mark.django_db
def test_question_column_sets_answer_css_class(event):
    with scopes_disabled():
        question = QuestionFactory(event=event)

    col = QuestionColumn(question=question)

    assert "answer" in col.attrs["td"]["class"]


@pytest.mark.parametrize(
    "is_descending", (False, True), ids=("ascending", "descending")
)
@pytest.mark.django_db
def test_question_column_order(event, is_descending):
    with scopes_disabled():
        question = QuestionFactory(event=event, target="submission")
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        AnswerFactory(question=question, submission=sub1, answer="Alpha")
        AnswerFactory(question=question, submission=sub2, answer="Bravo")
        qs = Submission.objects.filter(pk__in=[sub1.pk, sub2.pk])

    col = QuestionColumn(question=question)
    with scopes_disabled():
        ordered_qs, modified = col.order(qs, is_descending=is_descending)

    assert modified is True
    pks = list(ordered_qs.values_list("pk", flat=True))
    expected = [sub2.pk, sub1.pk] if is_descending else [sub1.pk, sub2.pk]
    assert pks == expected


@pytest.mark.django_db
def test_question_column_apply_custom_ordering_for_speaker(event):

    with scopes_disabled():
        question = QuestionFactory(event=event, target="speaker")
        speaker = SpeakerFactory(event=event)
        AnswerFactory(
            question=question, submission=None, speaker=speaker, answer="Test"
        )
        qs = SpeakerProfile.objects.filter(pk=speaker.pk)

    col = QuestionColumn(question=question)
    with scopes_disabled():
        result_qs, order_keys = col.apply_custom_ordering(qs, is_descending=False)

    assert len(order_keys) == 1
    assert f"_question_{question.id}_answer" in order_keys[0]


@pytest.mark.django_db
def test_question_column_render_with_answer(event):
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event, variant="string")
        submission = SubmissionFactory(event=event)
        AnswerFactory(question=question, submission=submission, answer="Hello world")
        qs = Submission.objects.filter(pk=submission.pk)

    table = TestTable(qs)
    table.short_questions = [question]
    table._question_model = "submission"
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request

    col = QuestionColumn(question=question, template_name="common/question_answer.html")
    bound_col = SimpleNamespace(default="", column=col)
    bound_row = SimpleNamespace(row_counter=0)

    with scopes_disabled():
        result = col.render(
            record=submission,
            table=table,
            value="",
            bound_column=bound_col,
            bound_row=bound_row,
        )

    assert "Hello world" in str(result)


@pytest.mark.django_db
def test_question_column_render_placeholder_without_answer(event):
    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event)
        submission = SubmissionFactory(event=event)
        qs = Submission.objects.filter(pk=submission.pk)

    table = TestTable(qs)
    table.short_questions = [question]
    table._question_model = "submission"

    col = QuestionColumn(question=question)

    with scopes_disabled():
        result = col.render(
            record=submission,
            table=table,
            value="",
            bound_column=SimpleNamespace(default=""),
            bound_row=SimpleNamespace(row_counter=0),
        )

    assert "&mdash;" in str(result)


@pytest.mark.django_db
def test_pretalx_table_order_by_setter_preserves_secondary_sort_from_different_column(
    event,
):
    """When _ordering_applied and a single new sort is set, preserve
    the secondary sort if it's on a different column."""
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    table._ordering_applied = True
    table._order_by = OrderByTuple(["code", "-title"])

    table.order_by = "code"

    order_strs = [str(o) for o in table._order_by]
    assert order_strs[0] == "code"
    assert len(order_strs) == 2
    assert order_strs[1] == "-title"


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_with_question_column(event):
    """_apply_ordering delegates to apply_custom_ordering for QuestionColumn."""

    class QTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event, target="submission")
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        AnswerFactory(question=question, submission=sub1, answer="Alpha")
        AnswerFactory(question=question, submission=sub2, answer="Bravo")
        qs = Submission.objects.filter(pk__in=[sub1.pk, sub2.pk])

    table = QTable(
        qs,
        event=event,
        extra_columns=[
            (
                f"question_{question.id}",
                QuestionColumn(verbose_name="Q", question=question),
            )
        ],
    )

    with scopes_disabled():
        ordered = table._apply_ordering(qs, [f"question_{question.id}"])

    pks = list(ordered.values_list("pk", flat=True))
    assert pks == [sub1.pk, sub2.pk]


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_accessor_with_negated_default(event):
    """When a column's order_by accessor already has '-' prefix and we sort
    ascending, the '-' should be removed."""

    class NegatedAccessorTable(PretalxTable):
        title = tables.Column(order_by=("-title",))

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        SubmissionFactory(event=event, title="Alpha")
        SubmissionFactory(event=event, title="Bravo")
        qs = Submission.objects.filter(event=event)

    table = NegatedAccessorTable(qs, event=event)

    ordered = table._apply_ordering(qs, ["title"])
    titles = list(ordered.values_list("title", flat=True))

    # order_by accessor is "-title", ascending removes the "-" → order_by("title")
    assert titles == ["Alpha", "Bravo"]


@pytest.mark.django_db
def test_actions_column_user_has_perm_denies(event):
    """When user.has_perm returns False and table doesn't have the permission
    attribute, the action should be skipped."""
    col = ActionsColumn(actions={"edit": {}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/"))
    request = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm, obj: False))
    table = SimpleNamespace(context={"request": request})

    result = col.render(record=record, table=table)

    assert "fa-edit" not in str(result)


@pytest.mark.django_db
def test_question_column_render_creates_context_when_missing(event):
    """QuestionColumn.render creates a Context when table.context is None."""

    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event, variant="string")
        submission = SubmissionFactory(event=event)
        AnswerFactory(question=question, submission=submission, answer="Context test")
        qs = Submission.objects.filter(pk=submission.pk)

    table = TestTable(qs)
    table.short_questions = [question]
    table._question_model = "submission"
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request
    # Explicitly set context to None to test the branch
    table.context = None

    col = QuestionColumn(question=question, template_name="common/question_answer.html")
    bound_col = SimpleNamespace(default="", column=col)
    bound_row = SimpleNamespace(row_counter=0)

    with scopes_disabled():
        result = col.render(
            record=submission,
            table=table,
            value="",
            bound_column=bound_col,
            bound_row=bound_row,
        )

    assert "Context test" in str(result)
    assert isinstance(table.context, Context)


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_model_field_fallback(event):
    """When bound_column.order_by is empty but the column name is a model
    field, _apply_ordering should use the field name directly."""

    class EmptyOrderByTable(PretalxTable):
        # Explicitly set order_by to empty tuple so bound_column.order_by is falsy
        title = tables.Column(order_by=())

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        SubmissionFactory(event=event, title="Bravo")
        SubmissionFactory(event=event, title="Alpha")
        qs = Submission.objects.filter(event=event)

    table = EmptyOrderByTable(qs, event=event)

    ordered = table._apply_ordering(qs, ["title"])
    titles = list(ordered.values_list("title", flat=True))

    assert titles == ["Alpha", "Bravo"]


@pytest.mark.django_db
def test_pretalx_table_order_by_setter_skips_invalid_column_name(event):
    """When _ordering_applied and a non-existent column is set, it is dropped."""
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    table._ordering_applied = True
    table._order_by = OrderByTuple(["title"])

    table.order_by = "nonexistent,title"

    assert [str(o) for o in table._order_by] == ["title"]


@pytest.mark.django_db
def test_pretalx_table_order_by_setter_with_multiple_valid_columns(event):
    """When _ordering_applied and multiple valid columns are set,
    the secondary-sort preservation logic is skipped."""
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    table._ordering_applied = True
    table._order_by = OrderByTuple(["code", "-title"])

    table.order_by = "title,code"

    assert [str(o) for o in table._order_by] == ["title", "code"]


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_skips_non_model_non_orderable_column(event):
    """Columns that aren't model fields and have no ordering mechanism are skipped."""

    class ComputedColumnTable(PretalxTable):
        title = tables.Column()
        computed = tables.Column(order_by=())

        class Meta:
            model = Submission
            fields = ("title", "computed")

    with scopes_disabled():
        SubmissionFactory(event=event, title="Alpha")
        qs = Submission.objects.filter(event=event)

    table = ComputedColumnTable(qs, event=event)

    ordered = table._apply_ordering(qs, ["computed"])
    titles = list(ordered.values_list("title", flat=True))

    assert titles == ["Alpha"]


@pytest.mark.django_db
def test_pretalx_table_configure_ignores_invalid_query_ordering(event):
    """When query ordering contains only invalid columns, it is not saved."""
    user = UserFactory()
    with scopes_disabled():
        qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=event)
    request = RequestFactory().get("/?sort=nonexistent")
    request.GET = request.GET.copy()
    request.GET.setlist("sort", ["nonexistent"])
    request.user = user

    table.configure(request)

    assert table._ordering_applied is False
    with scopes_disabled():
        prefs = user.get_event_preferences(event)
        saved = prefs.get("tables.SimpleTable.ordering")
    assert saved is None


@pytest.mark.django_db
def test_question_column_preserves_existing_td_attrs(event):
    with scopes_disabled():
        question = QuestionFactory(event=event)

    col = QuestionColumn(question=question, attrs={"td": {"class": "custom"}})

    assert col.attrs["td"]["class"] == "custom answer"


@pytest.mark.django_db
def test_question_column_render_reuses_existing_context(event):
    """QuestionColumn.render reuses table.context when it already exists."""

    class TestTable(QuestionColumnMixin, PretalxTable):
        title = tables.Column()

        class Meta:
            model = Submission
            fields = ("title",)

    with scopes_disabled():
        question = QuestionFactory(event=event, variant="string")
        submission = SubmissionFactory(event=event)
        AnswerFactory(question=question, submission=submission, answer="Reuse ctx")
        qs = Submission.objects.filter(pk=submission.pk)

    table = TestTable(qs)
    table.short_questions = [question]
    table._question_model = "submission"
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request
    table.context = Context({"existing_key": "preserved"})

    col = QuestionColumn(question=question, template_name="common/question_answer.html")
    bound_col = SimpleNamespace(default="", column=col)
    bound_row = SimpleNamespace(row_counter=0)

    with scopes_disabled():
        result = col.render(
            record=submission,
            table=table,
            value="",
            bound_column=bound_col,
            bound_row=bound_row,
        )

    assert "Reuse ctx" in str(result)
    assert table.context["existing_key"] == "preserved"
