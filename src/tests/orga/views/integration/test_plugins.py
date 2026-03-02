# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from tests.factories import EventFactory, UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_plugins_view_get_renders_for_organiser(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 200
    assert "grouped_plugins" in response.context


def test_plugins_view_user_without_permission_returns_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 404


def test_plugins_view_enable_plugin(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    assert not event.plugins

    response = client.post(
        event.orga_urls.plugins, {"plugin:tests.dummy_app": "enable"}
    )

    assert response.status_code == 302
    assert response.url == event.orga_urls.plugins
    event.refresh_from_db()
    assert "tests.dummy_app" in event.plugin_list
    with scopes_disabled():
        log = ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.plugins.enabled"
        )
        assert log.count() == 1
        assert log.first().data == {"plugin": "tests.dummy_app"}


def test_plugins_view_disable_plugin(client):
    event = EventFactory(plugins="tests.dummy_app")
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    assert "tests.dummy_app" in event.plugin_list

    response = client.post(
        event.orga_urls.plugins, {"plugin:tests.dummy_app": "disable"}
    )

    assert response.status_code == 302
    event.refresh_from_db()
    assert "tests.dummy_app" not in event.plugin_list
    with scopes_disabled():
        log = ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.plugins.disabled"
        )
        assert log.count() == 1
        assert log.first().data == {"plugin": "tests.dummy_app"}


def test_plugins_view_enable_unavailable_plugin_disables_instead(client, event):
    """Trying to enable a module not in available_plugins triggers the disable branch."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.plugins, {"plugin:nonexistent.module": "enable"}
    )

    assert response.status_code == 302
    event.refresh_from_db()
    assert "nonexistent.module" not in event.plugin_list


def test_plugins_view_non_plugin_post_keys_ignored(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.plugins, {"bogus_key": "enable"})

    assert response.status_code == 302
    event.refresh_from_db()
    assert not event.plugins
