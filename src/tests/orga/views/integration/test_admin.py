# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core import mail as djmail
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.models.settings import GlobalSettings
from pretalx.person.models import User
from pretalx.person.models.auth_token import UserApiToken
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserApiTokenFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def admin_user():
    return UserFactory(is_administrator=True)


def test_admin_dashboard_shows_admin_info(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("orga:admin.dashboard"))

    assert response.status_code == 200
    assert "Administrator information" in response.content.decode()


def test_admin_views_deny_non_administrators(client):
    user = UserFactory(is_administrator=False)
    client.force_login(user)

    response = client.get(reverse("orga:admin.dashboard"))

    assert response.status_code == 404


@override_settings(ADMINS=[])
def test_test_mail_no_admins_configured(client, admin_user):
    client.force_login(admin_user)

    response = client.post(reverse("orga:admin.test_mail"), follow=True)

    assert (
        "No administrator email addresses are configured" in response.content.decode()
    )


@override_settings(ADMINS=["admin@example.com"])
def test_test_mail_sends_email(client, admin_user):
    client.force_login(admin_user)
    djmail.outbox = []

    response = client.post(reverse("orga:admin.test_mail"))

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.dashboard")
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "test email" in djmail.outbox[0].subject.lower()

    # Follow redirect to verify success message
    response = client.get(response.url)
    assert "Test email sent successfully" in response.content.decode()


@override_settings(ADMINS=["admin@example.com"])
def test_test_mail_smtp_error_shows_failure(client, admin_user):
    client.force_login(admin_user)

    # Mocking task_send_transient.apply: need to simulate SMTP failure,
    # which is impossible with the locmem backend (system boundary).
    with patch(
        "pretalx.orga.views.admin.task_send_transient.apply",
        side_effect=OSError("Connection refused"),
    ):
        response = client.post(reverse("orga:admin.test_mail"), follow=True)

    assert "Failed to send test email" in response.content.decode()


def test_update_check_view_sets_ack(client, admin_user):
    client.force_login(admin_user)
    gs = GlobalSettings()
    assert not gs.settings.update_check_ack

    client.get(reverse("orga:admin.update"))

    gs.settings.flush()
    assert gs.settings.update_check_ack


def test_update_check_form_invalid_shows_error(client, admin_user):
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    response = client.post(
        url, {"update_check_email": "not-an-email", "update_check_enabled": "on"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors


def test_update_check_settings_save(client, admin_user):
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    client.post(
        url, {"update_check_email": "test@example.com", "update_check_enabled": "on"}
    )

    gs = GlobalSettings()
    gs.settings.flush()
    assert gs.settings.update_check_enabled
    assert gs.settings.update_check_email == "test@example.com"


def test_update_check_settings_disable(client, admin_user):
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    # First enable
    gs = GlobalSettings()
    gs.settings.update_check_enabled = True
    gs.settings.update_check_email = "old@example.com"

    # Then disable
    client.post(url, {"update_check_email": "", "update_check_enabled": ""})

    gs.settings.flush()
    assert not gs.settings.update_check_enabled
    assert not gs.settings.update_check_email


def _fake_update_check_response(method, url, **kwargs):
    payload = kwargs.get("json") or {}
    return SimpleNamespace(
        status=200,
        json=lambda: {
            "status": "ok",
            "version": {
                "latest": "1000.0.0",
                "yours": payload.get("version"),
                "updatable": True,
            },
            "plugins": {},
        },
    )


@patch(
    "pretalx.common.update_check.urllib3.request",
    side_effect=_fake_update_check_response,
)
def test_update_check_trigger(mock_urllib3_request, client, admin_user):
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    gs = GlobalSettings()
    assert not gs.settings.update_check_last

    response = client.post(url, {"trigger": "on"})

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.update")
    gs.settings.flush()
    assert gs.settings.update_check_last


@pytest.mark.parametrize(
    ("updatable", "expected_icon"),
    ((False, "fa-check-circle"), (True, "fa-arrow-circle-up")),
)
def test_update_check_view_renders_status_badges(
    client, admin_user, updatable, expected_icon
):
    client.force_login(admin_user)
    gs = GlobalSettings()
    gs.settings.update_check_enabled = True
    gs.settings.update_check_last = now()
    gs.settings.update_check_result = {
        "status": "ok",
        "version": {"latest": "1000.0.0", "yours": "1.0.0", "updatable": updatable},
        "plugins": {},
    }

    response = client.get(reverse("orga:admin.update"))
    content = response.content.decode()

    assert response.status_code == 200
    assert expected_icon in content


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.usefixtures("locmem_cache")
def test_admin_user_list_search_finds_users(
    client, admin_user, item_count, django_assert_num_queries
):
    client.force_login(admin_user)
    UserFactory.create_batch(item_count, name="SearchUser")

    with django_assert_num_queries(9):
        response = client.get(reverse("orga:admin.user.list"), {"q": "SearchUser"})

    assert response.status_code == 200
    assert "SearchUser" in response.content.decode()


@pytest.mark.parametrize("page", ("0", "9999", "99999999999999999999"))
def test_admin_user_list_out_of_range_page(client, admin_user, page):
    client.force_login(admin_user)
    UserFactory(name="SearchUser")

    response = client.get(
        reverse("orga:admin.user.list"), {"q": "SearchUser", "page": page}
    )

    assert response.status_code == 404


def test_admin_user_list_empty_without_search(client, admin_user):
    client.force_login(admin_user)
    UserFactory(name="Some User")

    response = client.get(reverse("orga:admin.user.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Some User" not in content
    assert "Show per page" not in content
    assert 'class="pagination' not in content


def test_admin_user_list_short_search_returns_empty(client, admin_user):
    client.force_login(admin_user)
    UserFactory(name="Ab User")

    response = client.get(reverse("orga:admin.user.list"), {"q": "Ab"})

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ab User" not in content


def test_admin_user_detail_shows_user_data(client, admin_user):
    target = UserFactory(name="Detail User", email="detail@example.com")
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert target.name in content
    assert set(response.context["tablist"].keys()) == {
        "teams",
        "submissions",
        "actions",
    }


def test_admin_user_detail_shows_submissions(client, admin_user):
    event = EventFactory()
    target = UserFactory()
    speaker = SpeakerFactory(user=target, event=event)
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_admin_user_detail_shows_teams(client, admin_user):
    event = EventFactory()
    target = make_orga_user(event)
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    assert "teams" in response.context
    assert len(response.context["teams"]) == 1


def test_admin_user_reset_password(client, admin_user):
    target = UserFactory()
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.user.list")
    target.refresh_from_db()
    assert target.pw_reset_token is not None


def test_admin_user_delete_shreds_user(client, admin_user):
    target = UserFactory()
    target_pk = target.pk
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": target.code})
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.user.list")
    assert not User.objects.filter(pk=target_pk).exists()


def test_admin_user_delete_deactivates_when_shred_fails(client, admin_user):
    event = EventFactory()
    target = make_orga_user(event)
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": target.code})
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert not target.is_active


def make_token_update_log(user):
    with scopes_disabled():
        token = UserApiTokenFactory(user=user, all_events=True)
        old_data = token.get_instance_data()
        token.all_events = False
        token.save()
        token.limit_events.set(
            [
                EventFactory(name="Alpha Conference"),
                EventFactory(name="Beta Conference"),
            ]
        )
        return token.log_action(
            "pretalx.user.token.update",
            person=user,
            old_data=old_data,
            new_data=token.get_instance_data(),
        )


def test_admin_user_detail_links_to_log_detail_for_entries_without_event(
    client, admin_user
):
    target = UserFactory()
    log = make_token_update_log(target)
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    assert (
        reverse("orga:admin.log.detail", kwargs={"pk": log.pk})
        in response.content.decode()
    )


def test_admin_log_detail_shows_changes(client):
    event = EventFactory(name="Alpha Conference")
    second_event = EventFactory(name="Beta Conference", organiser=event.organiser)
    target = make_orga_user(event)
    token = UserApiTokenFactory(
        user=target, all_events=True, endpoints={"events": ["list"]}
    )
    client.force_login(target)

    response = client.post(
        reverse("orga:user.token.edit", kwargs={"pk": token.pk}),
        {"limit_events": [event.pk, second_event.pk]},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        log = token.logged_actions().get(action_type="pretalx.user.token.update")

    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    response = client.get(reverse("orga:admin.log.detail", kwargs={"pk": log.pk}))

    assert response.status_code == 200
    changes = response.context["log"].changes
    assert set(changes) == {"all_events", "limit_events"}
    for field_name in ("all_events", "limit_events"):
        field = UserApiToken._meta.get_field(field_name)
        assert changes[field_name]["field"] == field
        assert changes[field_name]["label"] == field.verbose_name

    content = response.content.decode()
    assert str(UserApiToken._meta.get_field("all_events").verbose_name) in content
    assert str(UserApiToken._meta.get_field("limit_events").verbose_name) in content
    assert "Alpha Conference, Beta Conference" in content
    assert "All_events" not in content
    assert f"[{event.pk}, {second_event.pk}]" not in content


def test_admin_log_detail_denied_for_non_administrators(client):
    log = make_token_update_log(UserFactory())
    client.force_login(UserFactory())

    response = client.get(reverse("orga:admin.log.detail", kwargs={"pk": log.pk}))

    assert response.status_code == 404


def test_admin_log_detail_does_not_serve_event_entries(client, admin_user):
    event = EventFactory()
    log = event.log_action(
        "pretalx.event.update",
        person=admin_user,
        old_data={"name": "Old event name"},
        new_data={"name": "New event name"},
    )
    client.force_login(admin_user)

    response = client.get(reverse("orga:admin.log.detail", kwargs={"pk": log.pk}))

    assert response.status_code == 404


def test_healthcheck_returns_200(client, locmem_cache):
    response = client.get("/healthcheck/")

    assert response.status_code == 200
    assert response.content == b""


def test_healthcheck_returns_503_when_cache_unavailable(client):
    response = client.get("/healthcheck/")

    assert response.status_code == 503
    assert b"Cache not available" in response.content
