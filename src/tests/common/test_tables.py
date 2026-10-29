# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import django_tables2 as tables
import pytest
from django.contrib.auth.models import AnonymousUser
from django.db.models.functions import Lower
from django.template import Context
from django.test import RequestFactory
from django.utils.autoreload import file_changed
from django.utils.safestring import SafeString
from django_tables2.utils import OrderByTuple

from pretalx.common.forms.tables import MAX_SORT_LEVELS
from pretalx.common.tables import (
    ActionsColumn,
    BooleanColumn,
    ColourColumn,
    DateTimeColumn,
    DragsortTable,
    IndependentScoreColumn,
    PretalxTable,
    QuestionColumn,
    QuestionColumnMixin,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
    get_icon,
)
from pretalx.common.tables.columns import _cached_template
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


class DragsortTestTable(DragsortTable):
    title = tables.Column()

    class Meta:
        model = Submission
        fields = ("title",)

    def get_dragsort_url(self):
        return "/drag/"


class QuestionTestTable(QuestionColumnMixin, PretalxTable):
    title = tables.Column()

    class Meta:
        model = Submission
        fields = ("title",)


class SpeakerQuestionTestTable(QuestionColumnMixin, PretalxTable):
    name = tables.Column()

    class Meta:
        model = SpeakerProfile
        fields = ("name",)


def _visible(table):
    return {name for name, col in table.columns.items() if col.visible}


def _sort_request(user, *sort):
    request = RequestFactory().get("/")
    request.GET = request.GET.copy()
    request.GET.setlist("sort", list(sort))
    request.user = user
    return request


def _render_question(col, table, record):
    return str(
        col.render(
            record=record,
            table=table,
            value="",
            bound_column=SimpleNamespace(default="", column=col),
            bound_row=SimpleNamespace(row_counter=0),
        )
    )


def _buttons(rendered):
    """The inline buttons of an actions cell, before the dropdown menu."""
    return (
        str(rendered)
        .split("\n\n<details", 1)[0]
        .removeprefix('<div class="action-column">')
    )


def _menu_hrefs(rendered):
    return re.findall(r'href="([^"]*)"', str(rendered).split("<details", 1)[1])


EDIT_BUTTON = (
    '<a href="/edit/" class="table-action" aria-label="Edit" data-toggle="tooltip"'
    ' data-tooltip="Edit" data-placement="left"><i class="fa fa-edit"></i></a>'
)


def test_get_icon_returns_safe_html():
    result = get_icon("edit")

    assert isinstance(result, SafeString)
    assert result == '<i class="fa fa-edit"></i>'


def test_pretalx_table_column_introspection():
    table = SimpleTableWithHidden([])

    assert table.selected_columns == [("title", "Title"), ("code", "Code")]
    assert table.available_columns == [("internal", "Internal")]
    assert table._get_sortable_column_names() == {"title", "code", "internal"}
    assert table.canonical_column_names == ["title", "code", "internal"]
    assert table.current_ordering == []
    assert SimpleTable([], order_by="title,-code").current_ordering == [
        {"column": "title", "direction": "asc"},
        {"column": "code", "direction": "desc"},
    ]


def test_pretalx_table_set_columns_shows_valid_selection_in_order():
    table = SimpleTableWithHidden([])

    table._set_columns(["internal", "code", "nonexistent"])

    assert _visible(table) == {"internal", "code"}
    assert table.columns.names() == ["internal", "code", "title"]
    assert table.canonical_column_names == ["title", "code", "internal"]


def test_pretalx_table_exempt_columns_are_pinned_and_never_selectable():
    class TableWithPkAndActions(PretalxTable):
        pk = tables.Column()
        title = tables.Column()
        actions = tables.Column()

        class Meta:
            model = Submission
            fields = ("pk", "title", "actions")

    table = TableWithPkAndActions([])

    assert table.selected_columns == [("title", "Title")]

    table._set_columns(["title"])

    assert table.sequence == ["pk", "title", "actions"]


@pytest.mark.parametrize(
    ("ordering", "expected"),
    (
        pytest.param(["title", "-code"], ["title", "-code"], id="valid_columns"),
        pytest.param(["title", "-title"], ["title"], id="removes_duplicates"),
        pytest.param(["nonexistent"], None, id="all_invalid"),
        pytest.param([], [], id="empty"),
    ),
)
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
        pytest.param(
            ["-state"],
            ["title", "code", "-track"],
            ["-state", "code", "-track"],
            id="preserves_third_level",
        ),
        pytest.param(
            ["-state"],
            ["title", *(f"col{index}" for index in range(MAX_SORT_LEVELS))],
            ["-state", *(f"col{index}" for index in range(MAX_SORT_LEVELS - 1))],
            id="caps_at_max_sort_levels",
        ),
        pytest.param(
            ["title", "code", "-track"],
            ["code", "-title"],
            ["title", "code", "-track"],
            id="three_new_ignores_saved",
        ),
    ),
)
def test_pretalx_table_merge_ordering(new, saved, expected):
    table = SimpleTable([])

    result = table._merge_ordering(new, saved)

    assert result == expected


def test_pretalx_table_is_model_field():
    class NoMetaTable(PretalxTable):
        title = tables.Column()

    table = SimpleTable([])

    assert table._is_model_field("title") is True
    assert table._is_model_field("nonexistent") is False
    assert NoMetaTable([])._is_model_field("title") is False


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_by_model_field(event):
    SubmissionFactory(event=event, title="Alpha")
    SubmissionFactory(event=event, title="Bravo")
    qs = Submission.objects.filter(event=event)
    table = SimpleTable(qs, event=event)

    def titles(ordering):
        return list(table._apply_ordering(qs, ordering).values_list("title", flat=True))

    assert titles(["title"]) == ["Alpha", "Bravo"]
    assert titles(["-title"]) == ["Bravo", "Alpha"]


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_skips_unorderable_columns(event):
    class ComputedColumnTable(PretalxTable):
        title = tables.Column()
        computed = tables.Column(order_by=())

        class Meta:
            model = Submission
            fields = ("title", "computed")

    SubmissionFactory(event=event, title="Alpha")
    qs = Submission.objects.filter(event=event)
    table = ComputedColumnTable(qs, event=event)

    assert table._apply_ordering(qs, []) is qs
    assert list(table._apply_ordering(qs, ["nonexistent"])) == list(qs)
    assert list(table._apply_ordering(qs, ["computed"])) == list(qs)


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_with_function_order_column(event):
    SubmissionFactory(event=event, title="Bravo")
    SubmissionFactory(event=event, title="alpha")
    qs = Submission.objects.filter(event=event)

    table = SortableTestTable(qs, event=event)

    ordered = table._apply_ordering(qs, ["title"])
    titles = list(ordered.values_list("title", flat=True))

    assert titles == ["alpha", "Bravo"]


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_with_bound_column_order_by(event):
    class AccessorTable(PretalxTable):
        title = tables.Column(order_by=())
        code = tables.Column(order_by=("code",))
        negated = tables.Column(accessor="title", order_by=("-title",))

        class Meta:
            model = Submission
            fields = ("title", "code", "negated")

    s1 = SubmissionFactory(event=event, title="Bravo")
    s2 = SubmissionFactory(event=event, title="Alpha")
    qs = Submission.objects.filter(event=event)
    table = AccessorTable(qs, event=event)

    def titles(ordering):
        return list(table._apply_ordering(qs, ordering).values_list("title", flat=True))

    assert titles(["title"]) == ["Alpha", "Bravo"]
    assert titles(["negated"]) == ["Alpha", "Bravo"]
    assert titles(["-negated"]) == ["Bravo", "Alpha"]
    assert list(
        table._apply_ordering(qs, ["code"]).values_list("code", flat=True)
    ) == sorted([s1.code, s2.code])


@pytest.mark.django_db
def test_pretalx_table_apply_ordering_with_question_column(event):
    question = QuestionFactory(event=event, target="submission")
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=sub1, answer="Alpha")
    AnswerFactory(question=question, submission=sub2, answer="Bravo")
    qs = Submission.objects.filter(pk__in=[sub1.pk, sub2.pk])

    table = QuestionTestTable(
        qs,
        event=event,
        extra_columns=[
            (
                f"question_{question.id}",
                QuestionColumn(verbose_name="Q", question=question),
            )
        ],
    )

    ordered = table._apply_ordering(qs, [f"question_{question.id}"])

    pks = list(ordered.values_list("pk", flat=True))
    assert pks == [sub1.pk, sub2.pk]


def test_pretalx_table_configuration_form_only_with_hidden_or_default_columns():
    class DefaultColumnsTable(PretalxTable):
        title = tables.Column()
        code = tables.Column()
        default_columns = ["title"]

        class Meta:
            model = Submission
            fields = ("title", "code")

    assert SimpleTable([]).configuration_form is None
    hidden = SimpleTableWithHidden([])
    assert hidden.configuration_form.table is hidden
    assert DefaultColumnsTable([]).configuration_form is not None


@pytest.mark.django_db
def test_pretalx_table_configure_without_preferences_shows_meta_fields(event):
    qs = Submission.objects.filter(event=event)
    anonymous = RequestFactory().get("/")
    anonymous.user = AnonymousUser()
    authenticated = RequestFactory().get("/")
    authenticated.user = UserFactory()

    for request in (anonymous, authenticated):
        table = SimpleTable(qs, event=event)

        assert table.configure(request) is None
        assert _visible(table) == {"title", "code"}
        assert table._ordering_applied is False


@pytest.mark.django_db
def test_pretalx_table_configure_applies_saved_preferences(event):
    user = UserFactory()
    prefs = user.get_event_preferences(event)
    prefs.set(
        "tables.SimpleTableWithHidden.columns", ["title", "internal"], commit=True
    )
    prefs.set("tables.SimpleTableWithHidden.ordering", ["-title"], commit=True)
    prefs.set("tables.SimpleTableWithHidden.page_size", 25, commit=True)
    SubmissionFactory(event=event, title="Alpha")
    SubmissionFactory(event=event, title="Bravo")
    qs = Submission.objects.filter(event=event)
    table = SimpleTableWithHidden(qs, event=event)
    request = RequestFactory().get("/")
    request.user = user

    page_size = table.configure(request)

    assert page_size == 25
    assert _visible(table) == {"title", "internal"}
    assert list(table.data.data.values_list("title", flat=True)) == ["Bravo", "Alpha"]


@pytest.mark.django_db
def test_pretalx_table_configure_returns_page_size_without_event(event):
    user = UserFactory()
    prefs = user.get_event_preferences(None)
    prefs.set("tables.SimpleTable.page_size", 25, commit=True)
    qs = Submission.objects.filter(event=event)

    table = SimpleTable(qs, event=None)
    request = RequestFactory().get("/")
    request.user = user

    page_size = table.configure(request)

    assert page_size == 25


@pytest.mark.django_db
def test_pretalx_table_configure_applies_and_saves_valid_query_ordering(event):
    user = UserFactory()
    SubmissionFactory(event=event, title="Bravo")
    SubmissionFactory(event=event, title="Alpha")
    qs = Submission.objects.filter(event=event)
    prefs = user.get_event_preferences(event)

    table = SimpleTable(qs, event=event)
    table.configure(_sort_request(user, "nonexistent"))

    assert table._ordering_applied is False
    assert prefs.get("tables.SimpleTable.ordering") is None

    table = SimpleTable(qs, event=event)
    table.configure(_sort_request(user, "title"))

    assert table._ordering_applied is True
    assert list(table.data.data.values_list("title", flat=True)) == ["Alpha", "Bravo"]
    assert prefs.get("tables.SimpleTable.ordering") == ["title"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("table_cls", "saved_columns", "query", "with_header", "expected_visible"),
    (
        pytest.param(
            SimpleTableWithHidden,
            ["title", "code"],
            "print=title&print=internal",
            True,
            {"title", "internal"},
            id="header-overrides-saved",
        ),
        pytest.param(
            SimpleTableWithHidden,
            None,
            "print=internal",
            True,
            {"internal"},
            id="anonymous-with-header",
        ),
        pytest.param(
            SimpleTableWithHidden,
            ["title", "code"],
            "print=internal",
            False,
            {"title", "code"},
            id="no-header-ignores-print",
        ),
        pytest.param(
            SimpleTable,
            None,
            "print=",
            True,
            {"title", "code"},
            id="empty-print-value-falls-back",
        ),
        pytest.param(
            SimpleTable,
            None,
            "print=nonexistent&print=also_missing",
            True,
            {"title", "code"},
            id="all-invalid-columns-fall-back",
        ),
        pytest.param(
            SimpleTableWithHidden,
            None,
            "print=internal&print=nonexistent",
            True,
            {"internal"},
            id="partial-invalid-columns-dropped",
        ),
    ),
)
def test_pretalx_table_configure_print_query_param(
    event, table_cls, saved_columns, query, with_header, expected_visible
):
    user = UserFactory() if saved_columns is not None else None
    prefs_key = f"tables.{table_cls.__name__}.columns"
    if user is not None:
        user.get_event_preferences(event).set(prefs_key, saved_columns, commit=True)
    qs = Submission.objects.filter(event=event)

    table = table_cls(qs, event=event)
    extra = {"HTTP_HX_PRETALX_PRINT": "1"} if with_header else {}
    request = RequestFactory().get(f"/?{query}", **extra)
    request.user = user or AnonymousUser()

    table.configure(request)

    assert _visible(table) == expected_visible
    if user is not None:
        assert user.get_event_preferences(event).get(prefs_key) == saved_columns


@pytest.mark.parametrize(
    ("current", "value", "expected"),
    (
        pytest.param(["title", "-code"], "code", ["code"], id="drops_duplicate_level"),
        pytest.param(["code", "-title"], "code", ["code", "-title"], id="secondary"),
        pytest.param(
            ["code", "title", "-internal"],
            "code",
            ["code", "title", "-internal"],
            id="third_level",
        ),
        pytest.param(
            ["title", "-code", "internal"],
            "code",
            ["code", "internal"],
            id="duplicate_in_lower_level",
        ),
        pytest.param(["title"], "nonexistent,title", ["title"], id="invalid_name"),
        pytest.param(
            ["code", "-title"], "title,code", ["title", "code"], id="multiple_valid"
        ),
    ),
)
def test_pretalx_table_order_by_setter_after_ordering_applied_updates_display_only(
    current, value, expected
):
    table = SimpleTableWithHidden([])
    table._ordering_applied = True
    table._order_by = OrderByTuple(current)

    table.order_by = value

    assert [str(o) for o in table._order_by] == expected


def test_pretalx_table_order_by_setter_before_ordering_applied_uses_parent():
    table = SimpleTable([])

    table.order_by = "title"

    assert str(table.order_by[0]) == "title"


def test_dragsort_table():
    table = DragsortTestTable([])

    assert DragsortTable.is_dragsort is True
    assert table.orderable is False
    assert not table.order_by
    assert table.attrs["dragsort-url"] == "/drag/"
    assert table.row_attrs["dragsort-id"](SimpleNamespace(pk=42)) == 42


def test_sortable_column_order_function_lookup():
    expr = Lower("title")

    assert SortableColumn(order_by=expr).order_function_lookup == {"title": expr}
    assert SortableColumn(order_by="title").order_function_lookup == {}
    col = SortableColumn(order_by={"title": expr})
    assert col.order_function_lookup == {"title": expr}
    assert list(col.order_by) == ["title"]
    assert SortableTemplateColumn(
        template_code="{{ value }}", order_by=expr
    ).order_function_lookup == {"title": expr}


@pytest.mark.django_db
def test_sortable_column_order(event):
    SubmissionFactory(event=event, title="bravo")
    SubmissionFactory(event=event, title="Alpha")
    qs = Submission.objects.filter(event=event)
    col = SortableColumn(order_by=Lower("title"))

    assert SortableColumn(order_by="title").order(qs, is_descending=False) == (
        qs,
        False,
    )

    ordered_qs, modified = col.order(qs, is_descending=False)
    assert modified is True
    assert ordered_qs.query.order_by == ("_sort_title",)
    assert list(ordered_qs.values_list("title", flat=True)) == ["Alpha", "bravo"]

    ordered_qs, modified = col.order(qs, is_descending=True)
    assert modified is True
    assert ordered_qs.query.order_by == ("-_sort_title",)
    assert list(ordered_qs.values_list("title", flat=True)) == ["bravo", "Alpha"]


@pytest.mark.django_db
def test_template_column_renders_template_code_into_cells(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(template_code="{{ record.title }}")
        empty = TemplateColumn(template_code="{{ nothing }}")
        custom_empty = TemplateColumn(template_code="{{ nothing }}", placeholder="")
        named = TemplateColumn(
            template_code="{{ submission.title }}", context_object_name="submission"
        )
        callable_ctx = TemplateColumn(
            template_code="{{ extra_info }}",
            template_context={
                "extra_info": lambda record, table: f"info-{record.code}"
            },
        )
        static_ctx = TemplateColumn(
            template_code="{{ greeting }}", template_context={"greeting": "hello"}
        )

        class Meta:
            model = Submission
            fields = ("title",)

    sub = SubmissionFactory(event=event, title="My Talk")
    table = TplTable(Submission.objects.filter(pk=sub.pk), event=event)
    table.request = RequestFactory().get("/")

    row = list(table.rows)[0]

    assert row.get_cell("title") == "My Talk"
    assert row.get_cell("empty") == "&mdash;"
    assert row.get_cell("custom_empty") == ""
    assert row.get_cell("named") == "My Talk"
    assert row.get_cell("callable_ctx") == f"info-{sub.code}"
    assert row.get_cell("static_ctx") == "hello"
    assert row.get_cell_value("title") == "My Talk"
    assert row.get_cell_value("empty") == ""


@pytest.mark.django_db
def test_template_column_with_template_name(event):
    class TplTable(PretalxTable):
        answer_col = TemplateColumn(template_name="common/question_answer.html")

        class Meta:
            model = Submission
            fields = ()
            sequence = ("answer_col",)

    sub = SubmissionFactory(event=event)
    qs = Submission.objects.filter(pk=sub.pk)

    table = TplTable(qs, event=event)
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request
    table.context = Context({"answer": None})

    rendered = str(list(table.rows)[0].get_cell("answer_col"))

    assert rendered.strip() == "No response"


@pytest.mark.django_db
def test_template_column_escapes_inside_an_unescaped_page(event):
    class TplTable(PretalxTable):
        title = TemplateColumn(
            template_name="orga/tables/columns/submission_title.html"
        )

        class Meta:
            model = Submission
            fields = ("title",)

    sub = SubmissionFactory(event=event, title="<script>alert(1)</script>")
    table = TplTable(Submission.objects.filter(pk=sub.pk), event=event)
    table.request = RequestFactory().get("/")
    table.context = Context({}, autoescape=False)

    rendered = list(table.rows)[0].get_cell("title")

    assert "<script>" not in rendered
    assert table.context.autoescape is False


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        pytest.param(True, '<i class="fa fa-check"></i>', id="true"),
        pytest.param(False, '<i class="fa fa-times"></i>', id="false"),
        pytest.param(None, '<span class="text-muted">&mdash;</span>', id="none"),
    ),
)
def test_boolean_column_render(value, expected):
    col = BooleanColumn()

    result = col.render(value)

    assert isinstance(result, SafeString)
    assert result == expected


def test_datetime_column_render_in_event_timezone():
    col = DateTimeColumn()
    dt = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    event = SimpleNamespace(tz=ZoneInfo("Europe/Berlin"))

    def render(table, value):
        return col.render(record=None, table=table, value=value, bound_column=None)

    assert render(SimpleNamespace(event=event), dt) == "2024-06-15 16:30"
    assert render(SimpleNamespace(event=None), dt) == "2024-06-15 14:30"
    assert render(None, None) == "&mdash;"


def test_datetime_column_value():
    col = DateTimeColumn()

    assert col.value(datetime(2024, 6, 15, 14, 30, tzinfo=UTC)) == (
        "2024-06-15T14:30:00+00:00"
    )
    assert col.value(None) is None


def test_colour_column_render():
    col = ColourColumn()
    track = SimpleNamespace(color="#00ff00", name="Security")
    record = SimpleNamespace(color="#ff0000")

    assert col.render(value=track, record=SimpleNamespace()) == (
        '<span class="table-color-dot" style="--dot-color: #00ff00">Security</span>'
    )
    assert col.render(value="Red thing", record=record) == (
        '<span class="table-color-dot" style="--dot-color: #ff0000">Red thing</span>'
    )


def test_actions_column_merges_actions_with_defaults():
    col = ActionsColumn(
        actions={
            "edit": {"url": "custom_urls.edit"},
            "custom": {"icon": "star", "color": "warning", "url": "urls.custom"},
        }
    )

    assert col.header() == ""
    assert col.actions == {
        "edit": {
            "title": "Edit",
            "icon": "edit",
            "url": "custom_urls.edit",
            "color": "info",
            "condition": None,
            "permission": "update",
        },
        "custom": {"icon": "star", "color": "warning", "url": "urls.custom"},
    }


def test_actions_column_render_empty_without_pk_or_actions():
    table = SimpleNamespace(context={})

    assert (
        ActionsColumn(actions={"edit": {}}).render(
            record=SimpleNamespace(pk=None), table=table
        )
        == ""
    )
    assert (
        ActionsColumn(actions={}).render(record=SimpleNamespace(pk=1), table=table)
        == ""
    )


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        pytest.param(
            {
                "title": "Ping",
                "icon": "bell",
                "color": "primary",
                "extra_class": "ping-button",
                "permission": "update",
            },
            '<button type="button" class="table-action ping-button" aria-label="Ping"'
            ' data-toggle="tooltip" data-tooltip="Ping" data-placement="left">'
            '<i class="fa fa-bell"></i></button>',
            id="button_without_url",
        ),
        pytest.param(
            {"title": "Ping", "label": "Ping now", "icon": "bell", "color": "primary"},
            '<button type="button" class="btn btn-sm btn-primary" title="Ping">'
            '<i class="fa fa-bell"></i>Ping now</button>',
            id="labelled_button_carries_plain_title",
        ),
        pytest.param(
            {"color": "info", "label": "Click me", "permission": "update"},
            '<button type="button" class="btn btn-sm btn-info">Click me</button>',
            id="label_without_icon",
        ),
        pytest.param(
            {
                "icon": "copy",
                "title": "Copy",
                "color": "info",
                "extra_attrs": lambda record: f'data-id="{record.pk}"',
            },
            '<button type="button" class="table-action" aria-label="Copy"'
            ' data-toggle="tooltip" data-tooltip="Copy" data-placement="left"'
            ' data-id="99"><i class="fa fa-copy"></i></button>',
            id="callable_extra_attrs",
        ),
    ),
)
def test_actions_column_render_button(action, expected):
    col = ActionsColumn(actions={"ping": action})
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=SimpleNamespace(pk=99), table=table)

    assert _buttons(result) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    (
        pytest.param("urls.edit", "/events/test/edit/", id="dotted"),
        pytest.param("get_urls.edit", "/resolved/", id="dotted_callable"),
        pytest.param(lambda record: f"/view/{record.pk}/", "/view/42/", id="callable"),
    ),
)
def test_actions_column_render_link(url, expected):
    col = ActionsColumn(actions={"edit": {"url": url}})
    record = SimpleNamespace(
        pk=42,
        urls=SimpleNamespace(edit="/events/test/edit/"),
        get_urls=lambda: SimpleNamespace(edit="/resolved/"),
    )
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=record, table=table)

    assert _buttons(result) == EDIT_BUTTON.replace("/edit/", expected)
    assert _menu_hrefs(result) == [expected]


def test_actions_column_render_link_without_title_has_no_menu():
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
    table = SimpleNamespace(context={}, has_update_permission=True)

    result = col.render(record=SimpleNamespace(pk=42), table=table)

    assert str(result) == (
        '<div class="action-column"><a href="/view/42/" class="table-action">'
        '<i class="fa fa-eye"></i></a></div>'
    )


def test_actions_column_render_destructive_action_in_menu_with_next_url():
    col = ActionsColumn(actions={"edit": {}, "delete": {}})
    record = SimpleNamespace(
        pk=1, urls=SimpleNamespace(edit="/edit/", delete="/delete/")
    )
    request = SimpleNamespace(
        user=SimpleNamespace(has_perm=lambda perm, obj: True),
        get_full_path=lambda: "/current/?page=2",
    )
    table = SimpleNamespace(
        context={"request": request},
        has_update_permission=True,
        has_delete_permission=True,
    )

    result = str(col.render(record=record, table=table))

    assert _buttons(result) == EDIT_BUTTON
    assert _menu_hrefs(result) == ["/edit/", "/delete/?next=/current/%3Fpage%3D2"]
    assert "<hr>" in result
    assert "data-confirm-dialog" in result


def test_actions_column_condition_filters_per_record():
    col = ActionsColumn(actions={"edit": {"condition": lambda record: record.pk == 1}})
    table = SimpleNamespace(context={}, has_update_permission=True)

    shown = col.render(
        record=SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/")), table=table
    )
    hidden = col.render(record=SimpleNamespace(pk=2), table=table)

    assert _buttons(shown) == EDIT_BUTTON
    assert str(hidden) == '<div class="action-column"></div>'


def _user(allowed):
    return SimpleNamespace(has_perm=lambda perm, obj: allowed)


@pytest.mark.parametrize(
    ("table", "expected"),
    (
        pytest.param(
            SimpleNamespace(context={}, has_update_permission=True),
            True,
            id="table_flag_without_user",
        ),
        pytest.param(
            SimpleNamespace(
                context={"request": SimpleNamespace(user=_user(True))},
                has_update_permission=False,
            ),
            False,
            id="table_flag_beats_user",
        ),
        pytest.param(
            SimpleNamespace(context={"request": SimpleNamespace(user=_user(True))}),
            True,
            id="request_user_has_perm",
        ),
        pytest.param(
            SimpleNamespace(context={"request": SimpleNamespace(user=_user(False))}),
            False,
            id="request_user_denied",
        ),
        pytest.param(SimpleNamespace(context={}), False, id="without_user"),
        pytest.param(
            SimpleNamespace(context={}, user=_user(True)),
            True,
            id="table_user_without_request",
        ),
    ),
)
def test_actions_column_permission_check(table, expected):
    col = ActionsColumn(actions={"edit": {}})
    record = SimpleNamespace(pk=1, urls=SimpleNamespace(edit="/edit/"))

    result = col.render(record=record, table=table)

    if expected:
        assert _buttons(result) == EDIT_BUTTON
    else:
        assert str(result) == '<div class="action-column"></div>'


def test_independent_score_column_render():
    col = IndependentScoreColumn(category=SimpleNamespace(pk=5))
    record = SimpleNamespace(pk=1)

    def table(score):
        return SimpleNamespace(
            get_independent_score=lambda record, pk: score if pk == 5 else None
        )

    assert col.render(record=record, table=table(4.2)) == 4.2
    assert col.render(record=record, table=table(None)) == "&mdash;"


def test_question_column_mixin_question_model():
    assert QuestionTestTable([])._question_model == "submission"
    assert SpeakerQuestionTestTable([])._question_model == "speaker"


@pytest.mark.django_db
def test_question_column_mixin_get_question_columns(event):
    q1 = QuestionFactory(event=event, question="Favorite color")
    q2 = QuestionFactory(event=event, question="T-shirt size")
    table = QuestionTestTable([])

    table.short_questions = None
    assert table._get_question_columns() == []

    table.short_questions = [q1, q2]
    columns = table._get_question_columns()

    assert [name for name, _ in columns] == [f"question_{q1.id}", f"question_{q2.id}"]
    assert [column.question for _, column in columns] == [q1, q2]
    assert all(isinstance(column, QuestionColumn) for _, column in columns)


@pytest.mark.django_db
def test_question_column_mixin_get_answer_for_question_loads_cache_once(
    event, django_assert_num_queries
):
    question = QuestionFactory(event=event)
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    a1 = AnswerFactory(question=question, submission=sub1, answer="First")
    a2 = AnswerFactory(question=question, submission=sub2, answer="Second")
    qs = Submission.objects.filter(pk__in=[sub1.pk, sub2.pk])
    table = QuestionTestTable(qs)
    table.short_questions = [question]

    with django_assert_num_queries(3):
        result1 = table.get_answer_for_question(sub1, question.id)
        result2 = table.get_answer_for_question(sub2, question.id)

    assert result1 == a1
    assert result2 == a2
    assert table.get_answer_for_question(sub1, 999) is None


@pytest.mark.django_db
def test_question_column_mixin_get_answer_without_questions_or_records(event):
    table = QuestionTestTable([])
    table.short_questions = None

    assert table.get_answer_for_question(SimpleNamespace(pk=1), 999) is None

    table.short_questions = [QuestionFactory(event=event)]
    table._load_all_answers()

    assert table._answers_cache == {}


@pytest.mark.django_db
def test_question_column_mixin_speaker_answer(event):
    question = QuestionFactory(event=event, target="speaker")
    speaker = SpeakerFactory(event=event)
    answer = AnswerFactory(
        question=question, submission=None, speaker=speaker, answer="Yes"
    )
    qs = SpeakerProfile.objects.filter(pk=speaker.pk)

    table = SpeakerQuestionTestTable(qs)
    table.short_questions = [question]

    assert table.get_answer_for_question(speaker, question.id) == answer


@pytest.mark.django_db
def test_question_column_adds_answer_css_class(event):
    question = QuestionFactory(event=event)

    assert QuestionColumn(question=question).attrs["td"]["class"] == "answer"
    assert (
        QuestionColumn(question=question, attrs={"td": {"class": "custom"}}).attrs[
            "td"
        ]["class"]
        == "custom answer"
    )


@pytest.mark.django_db
def test_question_column_order(event):
    question = QuestionFactory(event=event, target="submission")
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=sub1, answer="Alpha")
    AnswerFactory(question=question, submission=sub2, answer="Bravo")
    qs = Submission.objects.filter(pk__in=[sub1.pk, sub2.pk])
    col = QuestionColumn(question=question)

    ordered_qs, modified = col.order(qs, is_descending=False)
    assert modified is True
    assert list(ordered_qs.values_list("pk", flat=True)) == [sub1.pk, sub2.pk]

    ordered_qs, modified = col.order(qs, is_descending=True)
    assert modified is True
    assert list(ordered_qs.values_list("pk", flat=True)) == [sub2.pk, sub1.pk]


@pytest.mark.django_db
def test_question_column_apply_custom_ordering_for_speaker(event):
    question = QuestionFactory(event=event, target="speaker")
    speaker = SpeakerFactory(event=event)
    AnswerFactory(question=question, submission=None, speaker=speaker, answer="Test")
    qs = SpeakerProfile.objects.filter(pk=speaker.pk)

    col = QuestionColumn(question=question)
    result_qs, order_keys = col.apply_custom_ordering(qs, is_descending=False)

    assert order_keys == [f"_question_{question.id}_answer"]
    assert list(result_qs) == [speaker]


@pytest.mark.django_db
def test_question_column_render_creates_context_when_missing(event):
    question = QuestionFactory(event=event, variant="string")
    answered = SubmissionFactory(event=event)
    unanswered = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=answered, answer="Context test")
    qs = Submission.objects.filter(pk__in=[answered.pk, unanswered.pk])
    table = QuestionTestTable(qs)
    table.short_questions = [question]
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request
    table.context = None
    col = QuestionColumn(question=question)

    assert _render_question(col, table, unanswered) == "&mdash;"
    assert _render_question(col, table, answered).strip() == "<p>Context test</p>"
    assert isinstance(table.context, Context)


@pytest.mark.django_db
def test_question_column_render_reuses_existing_context(event):
    question = QuestionFactory(event=event, variant="string")
    submission = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=submission, answer="Reuse ctx")
    qs = Submission.objects.filter(pk=submission.pk)
    table = QuestionTestTable(qs)
    table.short_questions = [question]
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    table.request = request
    table.context = Context({"existing_key": "preserved"})
    col = QuestionColumn(question=question)

    result = _render_question(col, table, submission)

    assert result.strip() == "<p>Reuse ctx</p>"
    assert table.context["existing_key"] == "preserved"


def test_cached_templates_are_dropped_when_a_file_changes():
    _cached_template("orga/tables/columns/review_tags.html")
    assert _cached_template.cache_info().currsize > 0

    file_changed.send(sender=None, file_path=Path("anything.html"))

    assert _cached_template.cache_info().currsize == 0
