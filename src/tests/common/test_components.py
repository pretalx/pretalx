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
}
ENGINE = Engine(
    loaders=[("django.template.loaders.locmem.Loader", TEMPLATES)],
    builtins=["pretalx.common.templatetags.components"],
)

component("probe", "probe.html", props=("color", "size"))
component("probe_preset", "probe.html", props=("color",), defaults={"color": "success"})
component("leak", "leak.html")


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
