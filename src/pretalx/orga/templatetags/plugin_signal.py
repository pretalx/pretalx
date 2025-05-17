from django import template
from django.utils.safestring import mark_safe

from pretalx.orga.signals import plugin_forms, plugin_html

register = template.Library()


@register.simple_tag(takes_context=True)
def get_plugin_forms(context, **kwargs):
    """Send a signal and return the concatenated list of all
    returned form.

    Usage::

        {% get_plugin_forms submission=submission as plugin_forms %}
        {% for plugin_form in plugin_forms %}
            {{ plugin_form }}
        {% endfor %}
    """
    forms = []
    request = context.request
    event = request.event
    for __, response in plugin_forms.send(event, request=request, **kwargs):
        if response:
            if not response:
                continue
            if isinstance(response, (list, tuple)):
                forms.extend(response)
            else:
                forms.append(response)
    return forms


@register.simple_tag(takes_context=True)
def get_plugin_html(context, **kwargs):
    """Send a signal and return the concatenated return values of all
    responses.

    Usage::

        {% get_plugin_html %}
    """
    html = []
    for __, response in plugin_html.send(
        context.request.event, request=context.request, **kwargs
    ):
        if response:
            html.append(response)
    return mark_safe("".join(html))
