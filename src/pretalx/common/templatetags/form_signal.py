from django import template
from django.utils.module_loading import import_string

register = template.Library()


@register.simple_tag(takes_context=True)
def form_signal(context, signal_name: str, **kwargs):
    """
    Usage:
        {% form_signal "path.to.signal" argument="value" ...  as extra_forms %}
        {% for form in extra_forms %}
            {{ form }}
        {% endfor %}
    """
    signal = import_string(signal_name)
    request = kwargs.pop("request", context.get("request"))
    sender = kwargs.pop("sender", getattr(request, "event", None))
    forms = []
    for _, response in signal.send_robust(sender=sender, request=request, **kwargs):
        if isinstance(response, Exception):
            continue
        if isinstance(response, list):
            forms.extend(response)
        elif response:
            forms.append(response)

    return forms
