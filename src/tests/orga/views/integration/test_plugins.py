# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from tests.factories import UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_plugins_view_enables_and_disables_plugins(client, event):
    client.force_login(UserFactory())

    assert client.get(event.orga_urls.plugins).status_code == 404

    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 200
    assert "grouped_plugins" in response.context
    assert not event.plugins

    response = client.post(
        event.orga_urls.plugins, {"plugin:tests.dummy_app": "enable"}
    )

    assert response.status_code == 302
    assert response.url == event.orga_urls.plugins
    event.refresh_from_db()
    assert event.plugin_list == ["tests.dummy_app"]

    for data in ({"bogus_key": "enable"}, {"plugin:nonexistent.module": "enable"}):
        response = client.post(event.orga_urls.plugins, data)
        assert response.status_code == 302, data
        event.refresh_from_db()
        assert event.plugin_list == ["tests.dummy_app"], data

    response = client.post(
        event.orga_urls.plugins, {"plugin:tests.dummy_app": "disable"}
    )

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.plugin_list == []
    with scopes_disabled():
        logs = ActivityLog.objects.filter(
            event=event, action_type__startswith="pretalx.event.plugins."
        ).order_by("pk")
        assert [(log.action_type, log.data) for log in logs] == [
            ("pretalx.event.plugins.enabled", {"plugin": "tests.dummy_app"}),
            ("pretalx.event.plugins.disabled", {"plugin": "tests.dummy_app"}),
        ]
