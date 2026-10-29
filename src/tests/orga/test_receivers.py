# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.orga.receivers import (
    add_html_above_session_pages,
    add_html_below_session_pages,
)
from tests.factories import EventFactory
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("handler", "settings_key"),
    (
        (add_html_above_session_pages, "agenda_session_above"),
        (add_html_below_session_pages, "agenda_session_below"),
    ),
    ids=("above", "below"),
)
@pytest.mark.parametrize(
    ("texts", "expected"),
    (
        ({"{key}": "**Hello**"}, "<p><strong>Hello</strong></p>"),
        ({"{key}": ""}, ""),
        ({}, ""),
    ),
    ids=("set", "empty", "unset"),
)
def test_add_html_session_page_renders_configured_text(
    handler, settings_key, texts, expected
):
    event = EventFactory(
        display_settings={
            "texts": {
                key.format(key=settings_key): value for key, value in texts.items()
            }
        }
    )
    request = make_request(event)

    assert handler(sender=event, request=request, submission=None) == expected
