# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.tables.filters import (
    EMPTY_VALUE,
    BooleanFilter,
    ChoiceFilter,
    FilterChoice,
    FilterContext,
    MultiChoiceFilter,
    SearchFilter,
    TableFilter,
    TableFilterSet,
    css_color,
)
from tests.factories.event import EventFactory
from tests.factories.submission import SubmissionFactory

pytestmark = [pytest.mark.unit]


def build(filters, query="", **options):
    context = FilterContext(**options)
    return TableFilterSet(filters, data=QueryDict(query), context=context)


def colours():
    return MultiChoiceFilter(
        name="colour",
        label="Colour",
        choices=[FilterChoice("red", "Red"), FilterChoice("blue", "Blue")],
    )


def test_unknown_values_are_ignored():
    filterset = build([colours()], "colour=red&colour=chartreuse")

    assert filterset.values["colour"] == ["red"]


def test_pills_carry_a_removal_url_without_the_removed_value():
    filterset = build([colours()], "colour=red&colour=blue")

    urls = [pill.remove_url for pill in filterset.pills]

    assert urls == ["?colour=blue", "?colour=red"]


def test_clear_url_drops_every_owned_parameter():
    filterset = build([colours()], "colour=red&page=2")

    assert filterset.clear_url == "?"


def test_clear_url_keeps_parameters_the_bar_does_not_own():
    filterset = build([colours()], "colour=red&sort=-code")

    assert filterset.clear_url == "?sort=-code"


def test_initials_apply_only_to_a_request_without_any_filter():
    class Seeded(MultiChoiceFilter):
        def get_initial(self):
            return ["red"]

    def seeded():
        return Seeded(
            name="colour",
            choices=[FilterChoice("red", "Red"), FilterChoice("blue", "Blue")],
        )

    assert build([seeded()]).values["colour"] == ["red"]
    assert build([seeded()], "colour=blue").values["colour"] == ["blue"]


def test_initials_may_be_a_single_value():
    class Seeded(ChoiceFilter):
        def get_initial(self):
            return "red"

    seeded = Seeded(
        name="colour",
        choices=[FilterChoice("red", "Red"), FilterChoice("blue", "Blue")],
    )

    assert build([seeded]).values["colour"] == "red"


class Defaulted(ChoiceFilter):
    def get_choices(self):
        return [FilterChoice("a", "A"), FilterChoice("b", "B")]

    def parse(self, data):
        return super().parse(data) or "b"

    def is_default(self, value):
        return value == "b"


def defaulted_filters():
    return [colours(), Defaulted(name="mode", label="Mode")]


def test_defaults_survive_other_filters():
    assert build(defaulted_filters()).values["mode"] == "b"
    assert build(defaulted_filters(), "colour=red").values["mode"] == "b"
    assert build(defaulted_filters(), "mode=a").values["mode"] == "a"


def test_defaults_do_not_count_as_active_filtering():
    pristine = build(defaulted_filters())
    chosen = build(defaulted_filters(), "mode=a")

    assert pristine.is_active is False
    assert pristine.pills == []
    assert chosen.is_active is True
    assert [pill.value for pill in chosen.pills] == ["a"]


def test_boolean_filter_is_tri_state():
    boolean = BooleanFilter(name="featured", label="Featured")

    assert build([boolean]).values["featured"] is None
    assert build([boolean], "featured=true").values["featured"] is True
    assert build([boolean], "featured=false").values["featured"] is False
    assert build([boolean], f"featured={EMPTY_VALUE}").values["featured"] is None


def test_boolean_filter_accepts_legacy_checkbox_value():
    assert build([BooleanFilter(name="featured")], "featured=on").values["featured"]


def test_param_names_cover_search_companions():
    filterset = build([SearchFilter(search=lambda *a, **k: None, fulltext=True)])

    assert filterset.param_names == ["fulltext", "q"]


def test_filters_without_choices_are_unavailable():
    empty = MultiChoiceFilter(name="colour", choices=[])
    filterset = build([empty], "colour=red")

    assert filterset.facets == []
    assert filterset.values["colour"] == []


@pytest.mark.parametrize(
    ("colour", "expected"),
    (
        ("", ""),
        ("#ff0000", "#ff0000"),
        ("--color-info", "var(--color-info, var(--color-neutral))"),
    ),
)
def test_css_colour_resolves_tokens_and_hexes(colour, expected):
    assert css_color(colour) == expected


def test_base_filter_is_inert():
    """The base class is a no-op in every direction, so subclasses opt in."""
    plain = TableFilter(name="anything", label="Anything")

    assert plain.get_choices() == []
    assert plain.get_pills("x") == []
    assert plain.filter("queryset", "x") == "queryset"
    assert plain.is_default("x") is False
    assert plain.selected_values("x") == ["x"]
    assert plain.selected_values("") == []


def test_pills_skip_values_that_are_no_longer_offered():
    assert colours().get_pills(["chartreuse"]) == []


def test_counts_are_empty_before_anything_is_filtered():
    filterset = build([colours()])

    assert filterset.filtered_count == 0
    assert filterset.total_count is None


def test_choices_may_be_a_callable():
    table_filter = MultiChoiceFilter(
        name="colour", choices=lambda bound: [FilterChoice("red", "Red")]
    )

    assert [choice.value for choice in table_filter.choices] == ["red"]


def test_single_choice_widget_groups_consecutive_options():
    table_filter = ChoiceFilter(
        name="action",
        label="Action",
        empty_label="All",
        choices=[
            FilterChoice("a", "A", group="First"),
            FilterChoice("b", "B", group="First"),
            FilterChoice("c", "C"),
        ],
    )

    markup = table_filter.render_widget("b")

    assert '<optgroup label="First">' in markup
    assert markup.count("<optgroup") == 1
    assert 'value="b" selected' in markup


def test_multi_widget_carries_counts_and_colours():
    table_filter = MultiChoiceFilter(
        name="state",
        label="State",
        with_counts=True,
        choices=[FilterChoice("accepted", "Accepted", color="--color-info", count=3)],
    )

    markup = table_filter.render_widget(["accepted"])

    assert "Accepted (3)" in markup
    assert 'data-color="var(--color-info, var(--color-neutral))"' in markup


def test_multi_widget_without_counts_lists_plain_options():
    table_filter = MultiChoiceFilter(
        name="colour",
        label="Colour",
        choices=[FilterChoice("red", "Red", color="--color-info")],
    )

    markup = table_filter.render_widget(["red"])

    assert 'value="red" selected' in markup
    assert ">Red</option>" in markup
    assert "(0)" not in markup


def test_is_set_is_false_for_unknown_filters():
    filterset = build([colours()], "colour=red")

    assert filterset.is_set("colour") is True
    assert filterset.is_set("nonexistent") is False


def test_boolean_filter_narrows_and_labels_both_answers():
    boolean = BooleanFilter(
        name="featured", label="Featured", yes_label="On", no_label="Off"
    )

    assert boolean.selected_values(True) == ["true"]
    assert boolean.selected_values(False) == ["false"]
    assert boolean.selected_values(None) == [EMPTY_VALUE]
    assert [pill.label for pill in boolean.get_pills(True)] == ["Featured: On"]
    assert [pill.label for pill in boolean.get_pills(False)] == ["Featured: Off"]


def test_boolean_widget_renders_segments_with_the_empty_sentinel():
    boolean = BooleanFilter(
        name="featured", label="Featured", yes_label="On", no_label="Off"
    )

    markup = boolean.render_widget(None, form_id="filter-form-x")

    assert markup.count('type="radio"') == 3
    assert f'value="{EMPTY_VALUE}"' in markup
    assert 'aria-label="Featured"' in markup
    assert 'form="filter-form-x"' in markup


@pytest.mark.django_db
def test_boolean_filter_narrows_a_queryset():
    event = EventFactory()
    featured = SubmissionFactory(event=event, is_featured=True)
    SubmissionFactory(event=event, is_featured=False)

    filterset = build([BooleanFilter(name="is_featured")], "is_featured=true")

    assert list(filterset.filter(event.submissions.all())) == [featured]
