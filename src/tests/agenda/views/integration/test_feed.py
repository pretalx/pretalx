# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.common.text.xml import strip_control_characters

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_feed_renders_atom(
    client, public_event_with_schedule, item_count, django_assert_num_queries
):
    event = public_event_with_schedule
    with scope(event=event):
        for i in range(1, item_count):
            event.release_schedule(f"v{i + 1}")

    with django_assert_num_queries(9):
        response = client.get(event.urls.feed)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/atom+xml")
    content = response.content.decode()
    assert strip_control_characters(event.name) in content
    assert content.count("<entry>") == item_count
    assert "changelog" in content
    assert "#v1" in content


def test_schedule_feed_404_without_permission(client, published_talk_slot):
    event = published_talk_slot.event
    event.is_public = False
    event.save()
    response = client.get(event.urls.feed)

    assert response.status_code == 404
