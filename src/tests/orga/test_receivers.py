import pytest

from pretalx.orga.receivers import (
    add_html_above_session_pages,
    add_html_below_session_pages,
)
from tests.factories import EventFactory
from tests.utils import make_request

pytestmark = pytest.mark.unit

_SESSION_PAGE_HANDLERS = pytest.mark.parametrize(
    ("handler", "settings_key"),
    (
        (add_html_above_session_pages, "agenda_session_above"),
        (add_html_below_session_pages, "agenda_session_below"),
    ),
    ids=("above", "below"),
)


@_SESSION_PAGE_HANDLERS
@pytest.mark.django_db
def test_add_html_session_page_returns_rich_text_when_set(handler, settings_key):
    event = EventFactory()
    event.display_settings["texts"] = {settings_key: "**Hello**"}
    event.save()
    request = make_request(event)

    result = handler(sender=event, request=request, submission=None)

    assert "Hello" in result


@_SESSION_PAGE_HANDLERS
@pytest.mark.django_db
def test_add_html_session_page_returns_empty_when_unset(handler, settings_key):
    event = EventFactory()
    request = make_request(event)

    result = handler(sender=event, request=request, submission=None)

    assert result == ""


@_SESSION_PAGE_HANDLERS
@pytest.mark.django_db
def test_add_html_session_page_returns_empty_for_empty_string(handler, settings_key):
    event = EventFactory()
    event.display_settings["texts"] = {settings_key: ""}
    event.save()
    request = make_request(event)

    result = handler(sender=event, request=request, submission=None)

    assert result == ""
