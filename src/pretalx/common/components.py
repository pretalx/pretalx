# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django import template
from django.template.base import Node, TemplateSyntaxError

register = template.Library()


class ComponentNode(Node):
    def __init__(self, template_name, base_values, attributes, nodelist=None):
        self.template_name = template_name
        self.base_values = base_values
        self.attributes = attributes
        self.nodelist = nodelist
        self.template = None

    def render(self, context):
        if self.template is None:
            # Cache so development isn't slow
            self.template = context.template.engine.get_template(self.template_name)
        values = dict(self.base_values)
        for name, expression in self.attributes.items():
            values[name] = expression.resolve(context)
        if self.nodelist is not None:
            values["children"] = self.nodelist.render(context)
        return self.template.render(context.new(values))


def parse_attributes(parser, token, props):
    bits = token.split_contents()
    tag_name = bits[0]
    attributes = {}
    for bit in bits[1:]:
        name, separator, value = bit.partition("=")
        if not separator or not value:
            raise TemplateSyntaxError(
                f"{{% {tag_name} %}} takes attribute=value pairs, but got {bit!r}."
            )
        if name not in props:
            accepted = ", ".join(sorted(props)) or "none"
            raise TemplateSyntaxError(
                f"{{% {tag_name} %}} got an unknown attribute {name!r}. "
                f"Accepted attributes: {accepted}."
            )
        if name in attributes:
            raise TemplateSyntaxError(
                f"{{% {tag_name} %}} got the attribute {name!r} twice."
            )
        attributes[name] = parser.compile_filter(value)
    return attributes


def component(name, template_name, props=(), defaults=None):
    """Register ``{% name %}`` and ``{% #name %}…{% /name %}``"""
    props = frozenset(props)
    base_values = dict.fromkeys(props, "")
    base_values["children"] = ""
    base_values.update(defaults or {})

    def compile_inline(parser, token):
        return ComponentNode(
            template_name, base_values, parse_attributes(parser, token, props)
        )

    def compile_block(parser, token):
        attributes = parse_attributes(parser, token, props)
        nodelist = parser.parse((f"/{name}",))
        parser.delete_first_token()
        return ComponentNode(template_name, base_values, attributes, nodelist=nodelist)

    register.tag(name, compile_inline)
    register.tag(f"#{name}", compile_block)
