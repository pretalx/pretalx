import pytest

from pretalx.cfp.signals import html_head
from pretalx.common.templatetags.html_signal import html_signal

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_html_signal_no_receivers(event):
    """Signal with no active receivers returns empty string."""
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert result == ""


@pytest.mark.django_db
def test_html_signal_with_receiver(event, register_signal_handler):
    def handler(signal, sender, **kwargs):
        return "<div>test</div>"

    register_signal_handler(html_head, handler)
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert "<div>test</div>" in result


@pytest.mark.django_db
def test_html_signal_concatenates_responses(event, register_signal_handler):
    def handler1(signal, sender, **kwargs):
        return "<span>one</span>"

    def handler2(signal, sender, **kwargs):
        return "<span>two</span>"

    register_signal_handler(html_head, handler1)
    register_signal_handler(html_head, handler2)
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert "<span>one</span>" in result
    assert "<span>two</span>" in result


@pytest.mark.django_db
def test_html_signal_skips_none_responses(event, register_signal_handler):
    def handler(signal, sender, **kwargs):
        return None

    register_signal_handler(html_head, handler)
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert result == ""
