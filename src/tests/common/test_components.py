# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.template import Context, Engine
from django.template.base import TemplateSyntaxError

from pretalx.common.components import component

pytestmark = pytest.mark.unit

TEMPLATES = {
    "probe.html": '<b class="{{ color }}{% if size %} {{ size }}{% endif %}">{{ children }}</b>',
    "leak.html": "[{{ outer }}]",
    "slotted.html": "<b>{{ children }}</b>{% if extra %}<i>{{ extra }}</i>{% endif %}",
    "aside.html": "<b>{{ children }}</b>{% if note %}<i>{{ note }}</i>{% endif %}",
    "late.html": "{% #slot extra %}x{% /slot %}",
}
ENGINE = Engine(
    loaders=[("django.template.loaders.locmem.Loader", TEMPLATES)],
    builtins=["pretalx.common.templatetags.components"],
)

component("probe", "probe.html", props=("color", "size"))
component("probe_preset", "probe.html", props=("color",), defaults={"color": "success"})
component("leak", "leak.html")
component("slotted", "slotted.html", slots=("extra",))
component("aside", "aside.html", slots=("note",))


def render(source, context=None):
    return ENGINE.from_string(source).render(Context(context or {}))


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ('{% probe color="red" %}', '<b class="red"></b>'),
        (
            '{% #probe color="red" size="lg" %}Save{% /probe %}',
            '<b class="red lg">Save</b>',
        ),
        ("{% #probe color=color %}{{ label }}{% /probe %}", '<b class="red">Save</b>'),
        ("{% probe color=color|upper %}", '<b class="RED"></b>'),
        ("{% probe %}", '<b class=""></b>'),
    ),
    ids=("inline", "block", "context_variables", "filtered_value", "no_attributes"),
)
def test_component_renders(source, expected):
    assert render(source, {"color": "red", "label": "Save"}) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("{% #slotted %}Save{% /slotted %}", "<b>Save</b>"),
        (
            "{% #slotted %}Save{% #slot extra %}now{% /slot %}{% /slotted %}",
            "<b>Save</b><i>now</i>",
        ),
        (
            "{% #slotted %}Save{% if color %}{% #slot extra %}{{ color }}{% /slot %}{% endif %}{% /slotted %}",
            "<b>Save</b><i>red</i>",
        ),
        (
            "{% #slotted %}{% #slotted %}in{% #slot extra %}deep{% /slot %}{% /slotted %}{% /slotted %}",
            "<b><b>in</b><i>deep</i></b>",
        ),
    ),
    ids=("unfilled", "filled", "conditional", "nested_components"),
)
def test_component_slots(source, expected):
    assert render(source, {"color": "red"}) == expected


def test_component_slot_rejects_unknown_name_when_compiling():
    with pytest.raises(TemplateSyntaxError, match="Accepted slots: extra"):
        ENGINE.from_string("{% #slotted %}{% #slot nope %}x{% /slot %}{% /slotted %}")


def test_component_slot_of_a_nested_component_is_not_ours():
    assert (
        render(
            "{% #slotted %}{% #aside %}in{% #slot note %}x{% /slot %}{% /aside %}{% /slotted %}"
        )
        == "<b><b>in</b><i>x</i></b>"
    )


@pytest.mark.parametrize(
    "source",
    (
        "{% #slot extra %}x{% /slot %}",
        '{% #slotted %}{% include "late.html" %}{% /slotted %}',
    ),
    ids=("bare", "included"),
)
def test_component_slot_outside_a_component_block(source):
    template = ENGINE.from_string(source)
    with pytest.raises(TemplateSyntaxError, match="only allowed directly inside"):
        template.render(Context())


def test_component_slot_requires_a_name():
    with pytest.raises(TemplateSyntaxError, match="exactly one argument"):
        ENGINE.from_string("{% #slot %}x{% /slot %}")


def test_component_does_not_see_the_calling_context():
    assert render("{% leak %}", {"outer": "visible"}) == "[]"


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("{% probe_preset %}", '<b class="success"></b>'),
        ('{% probe_preset color="danger" %}', '<b class="danger"></b>'),
    ),
    ids=("default_applied", "default_overridden"),
)
def test_component_defaults(source, expected):
    assert render(source) == expected


@pytest.mark.parametrize(
    ("source", "message"),
    (
        ('{% probe colour="red" %}', "unknown attribute 'colour'"),
        ('{% probe aria-label="x" %}', "unknown attribute 'aria-label'"),
        ('{% #probe colour="red" %}Save{% /probe %}', "unknown attribute 'colour'"),
        ('{% leak color="red" %}', "Accepted attributes: none"),
        ("{% probe color %}", "takes attribute=value pairs, but got 'color'"),
        ("{% probe color= %}", "takes attribute=value pairs, but got 'color='"),
        ('{% probe color="a" color="b" %}', "got the attribute 'color' twice"),
    ),
    ids=(
        "typo",
        "dashed_name",
        "block_form",
        "no_props",
        "missing_value",
        "empty_value",
        "duplicate",
    ),
)
def test_component_rejects_bad_attributes_when_compiling(source, message):
    with pytest.raises(TemplateSyntaxError, match=message):
        ENGINE.from_string(source)


def test_component_lists_accepted_attributes():
    with pytest.raises(TemplateSyntaxError, match="Accepted attributes: color, size"):
        ENGINE.from_string("{% probe nope=1 %}")


def test_component_lists_slots_with_accepted_attributes():
    with pytest.raises(TemplateSyntaxError, match="Slots: extra"):
        ENGINE.from_string('{% #slotted extra="x" %}Save{% /slotted %}')


def test_component_rejects_a_name_that_is_both_prop_and_slot():
    with pytest.raises(ValueError, match="both a prop and a slot"):
        component("clash", "slotted.html", props=("extra",), slots=("extra",))


def test_component_template_is_resolved_once_per_node(monkeypatch):
    calls = []
    original = ENGINE.get_template

    def counting(template_name):
        calls.append(template_name)
        return original(template_name)

    monkeypatch.setattr(ENGINE, "get_template", counting)
    template = ENGINE.from_string('{% probe color="red" %}')
    template.render(Context())
    template.render(Context())

    assert calls == ["probe.html"]
