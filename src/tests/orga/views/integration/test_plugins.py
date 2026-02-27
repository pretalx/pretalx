import pytest
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from tests.factories import UserFactory
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_plugins_view_get_renders_for_organiser(client, event):
    """GET returns 200 with plugin data for an organiser with event settings permission."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 200
    assert "grouped_plugins" in response.context


@pytest.mark.django_db
def test_plugins_view_anonymous_redirects_to_login(client, event):
    """Anonymous users are redirected to the event login page."""
    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 302
    assert f"/orga/event/{event.slug}/login/" in response.url


@pytest.mark.django_db
def test_plugins_view_user_without_permission_returns_404(client, event):
    """A user without event settings permission gets 404."""
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 404


@pytest.mark.django_db
def test_plugins_view_orga_without_settings_permission_returns_404(client, event):
    """An organiser without can_change_event_settings gets 404."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=False)
    client.force_login(user)

    response = client.get(event.orga_urls.plugins)

    assert response.status_code == 404


@pytest.mark.django_db
def test_plugins_view_enable_plugin(client, event):
    """POSTing plugin:module=enable adds the plugin to the event."""
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


@pytest.mark.django_db
def test_plugins_view_enable_plugin_logs_action(client, event):
    """Enabling a plugin creates an activity log entry."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    client.post(event.orga_urls.plugins, {"plugin:tests.dummy_app": "enable"})

    with scopes_disabled():
        log = ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.plugins.enabled"
        )
        assert log.count() == 1
        assert log.first().data == {"plugin": "tests.dummy_app"}


@pytest.mark.django_db
def test_plugins_view_disable_plugin(client, event):
    """POSTing plugin:module=disable removes the plugin from the event."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        event.enable_plugin("tests.dummy_app")
        event.save()
    client.force_login(user)
    assert "tests.dummy_app" in event.plugin_list

    response = client.post(
        event.orga_urls.plugins, {"plugin:tests.dummy_app": "disable"}
    )

    assert response.status_code == 302
    event.refresh_from_db()
    assert "tests.dummy_app" not in event.plugin_list


@pytest.mark.django_db
def test_plugins_view_disable_plugin_logs_action(client, event):
    """Disabling a plugin creates an activity log entry."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        event.enable_plugin("tests.dummy_app")
        event.save()
    client.force_login(user)

    client.post(event.orga_urls.plugins, {"plugin:tests.dummy_app": "disable"})

    with scopes_disabled():
        log = ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.plugins.disabled"
        )
        assert log.count() == 1
        assert log.first().data == {"plugin": "tests.dummy_app"}


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_plugins_view_non_plugin_post_keys_ignored(client, event):
    """POST keys not starting with 'plugin:' are ignored."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.plugins, {"bogus_key": "enable"})

    assert response.status_code == 302
    event.refresh_from_db()
    assert not event.plugins


@pytest.mark.django_db
def test_plugins_view_redirects_after_post(client, event):
    """POST always redirects to the plugins URL."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.plugins, {})

    assert response.status_code == 302
    assert response.url == event.orga_urls.plugins
