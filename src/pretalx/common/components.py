# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django import template
from django.template.base import Node, TemplateSyntaxError
from django.template.loader import get_template as get_configured_template

register = template.Library()

SLOT_STACK = "component_slots"


class ComponentNode(Node):
    def __init__(self, template_name, base_values, attributes, slots, nodelist=None):
        self.template_name = template_name
        self.base_values = base_values
        self.attributes = attributes
        self.slots = slots
        self.nodelist = nodelist
        self.template = None

    def render(self, context):
        component_template = self.template
        if component_template is None:
            if context.template is None:
                component_template = get_configured_template(
                    self.template_name
                ).template
            else:
                # Cache so development isn't slow
                component_template = self.template = (
                    context.template.engine.get_template(self.template_name)
                )
        values = dict(self.base_values)
        for name, expression in self.attributes.items():
            values[name] = expression.resolve(context)
        if self.nodelist is not None:
            stack = context.render_context.setdefault(SLOT_STACK, [])
            stack.append(dict.fromkeys(self.slots, ""))
            try:
                values["children"] = self.nodelist.render(context)
            finally:
                values.update(stack.pop())
        return component_template.render(context.new(values))


class SlotNode(Node):
    def __init__(self, name, nodelist):
        self.name = name
        self.nodelist = nodelist

    def render(self, context):
        stack = context.render_context.get(SLOT_STACK)
        if not stack:
            raise TemplateSyntaxError(
                f"{{% #slot {self.name} %}} is only allowed directly inside a "
                f"component block, not in a template pulled in with {{% include %}}."
            )
        slots = stack[-1]
        if self.name not in slots:
            accepted = ", ".join(sorted(slots)) or "none"
            raise TemplateSyntaxError(
                f"{{% #slot {self.name} %}} is not a slot of the enclosing component. "
                f"Accepted slots: {accepted}."
            )
        slots[self.name] = self.nodelist.render(context)
        return ""


@register.tag("#slot")
def compile_slot(parser, token):
    bits = token.split_contents()
    if len(bits) != 2:
        raise TemplateSyntaxError("{% #slot %} takes exactly one argument, its name.")
    nodelist = parser.parse(("/slot",))
    parser.delete_first_token()
    return SlotNode(bits[1], nodelist)


def find_slots(nodelist):
    """Slots of this component only – nested components own the ones inside them."""
    for node in nodelist:
        if isinstance(node, SlotNode):
            yield node
        elif not isinstance(node, ComponentNode):
            for attribute in node.child_nodelists:
                child = getattr(node, attribute, None)
                if child:
                    yield from find_slots(child)


def parse_attributes(parser, token, props, slots=()):
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
            known_slots = f" Slots: {', '.join(sorted(slots))}." if slots else ""
            raise TemplateSyntaxError(
                f"{{% {tag_name} %}} got an unknown attribute {name!r}. "
                f"Accepted attributes: {accepted}.{known_slots}"
            )
        if name in attributes:
            raise TemplateSyntaxError(
                f"{{% {tag_name} %}} got the attribute {name!r} twice."
            )
        attributes[name] = parser.compile_filter(value)
    return attributes


def component(name, template_name, props=(), defaults=None, slots=()):
    """Register ``{% name %}`` and ``{% #name %}…{% /name %}``"""
    props = frozenset(props)
    slots = frozenset(slots)
    if clash := props & slots:
        raise ValueError(
            f"Component {name!r} declares {', '.join(sorted(clash))} as both "
            f"a prop and a slot, so the slot would overwrite the passed value."
        )
    base_values = dict.fromkeys(props | slots, "")
    base_values["children"] = ""
    base_values.update(defaults or {})

    def compile_inline(parser, token):
        return ComponentNode(
            template_name,
            base_values,
            parse_attributes(parser, token, props, slots),
            slots,
        )

    def compile_block(parser, token):
        attributes = parse_attributes(parser, token, props, slots)
        nodelist = parser.parse((f"/{name}",))
        parser.delete_first_token()
        for node in find_slots(nodelist):
            if node.name not in slots:
                accepted = ", ".join(sorted(slots)) or "none"
                raise TemplateSyntaxError(
                    f"{{% #slot {node.name} %}} is not a slot of {{% #{name} %}}. "
                    f"Accepted slots: {accepted}."
                )
        return ComponentNode(
            template_name, base_values, attributes, slots, nodelist=nodelist
        )

    register.tag(name, compile_inline)
    register.tag(f"#{name}", compile_block)
