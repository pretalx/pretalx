# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.models.settings import GlobalSettings
from pretalx.person.enums import EmailVerificationState
from pretalx.person.models import User
from pretalx.person.models.auth_token import UserApiToken
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    ProfilePictureFactory,
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


def test_admin_dashboard_shows_admin_info(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("orga:admin.dashboard"))

    assert response.status_code == 200
    assert "Administrator information" in response.content.decode()


def test_admin_views_deny_anonymous_and_non_administrators(client, event):
    orga_user = make_orga_user(
        event, can_change_event_settings=True, can_change_teams=True
    )
    target = UserFactory(
        name="Secret Person", email_verification_state=EmailVerificationState.VERIFIED
    )
    log = make_token_update_log(target)
    verification_url = reverse(
        "orga:admin.user.verification", kwargs={"code": target.code}
    )
    urls = [
        reverse("orga:admin.dashboard"),
        reverse("orga:admin.update"),
        reverse("orga:admin.user.list"),
        reverse("orga:admin.user.detail", kwargs={"code": target.code}),
        reverse("orga:admin.log.detail", kwargs={"pk": log.pk}),
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 302, url
        assert response.url == f"/orga/login/?next={url}", url
    response = client.post(verification_url, {"state": "unverified"})
    assert response.status_code == 302
    assert response.url == f"/orga/login/?next={verification_url}"

    client.force_login(orga_user)
    for url in urls:
        assert client.get(url).status_code == 404, url
    response = client.post(verification_url, {"state": "unverified"})
    assert response.status_code == 404
    target.refresh_from_db()
    assert target.email_verification_state == EmailVerificationState.VERIFIED


@override_settings(ADMINS=[])
def test_test_mail_no_admins_configured(client, admin_user):
    client.force_login(admin_user)

    response = client.post(reverse("orga:admin.test_mail"), follow=True)

    assert (
        "No administrator email addresses are configured" in response.content.decode()
    )


@override_settings(ADMINS=["admin@example.com"])
def test_test_mail_reports_success_and_failure(client, admin_user):
    client.force_login(admin_user)
    djmail.outbox = []

    response = client.post(reverse("orga:admin.test_mail"))

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.dashboard")
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "test email" in djmail.outbox[0].subject.lower()
    response = client.get(response.url)
    assert "Test email sent successfully" in response.content.decode()

    # Mocking task_send_transient.apply: need to simulate SMTP failure,
    # which is impossible with the locmem backend (system boundary).
    with patch(
        "pretalx.orga.views.admin.task_send_transient.apply",
        side_effect=OSError("Connection refused"),
    ):
        response = client.post(reverse("orga:admin.test_mail"), follow=True)

    assert "Failed to send test email" in response.content.decode()
    assert len(djmail.outbox) == 1


def test_update_check_settings_round_trip(client, admin_user):
    client.force_login(admin_user)
    url = reverse("orga:admin.update")
    gs = GlobalSettings()
    assert not gs.settings.update_check_ack

    response = client.get(url)

    assert response.status_code == 200
    gs.settings.flush()
    assert gs.settings.update_check_ack

    response = client.post(
        url, {"update_check_email": "not-an-email", "update_check_enabled": "on"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors == {
        "update_check_email": ["Enter a valid email address."]
    }
    gs.settings.flush()
    assert gs.settings.update_check_email == ""

    response = client.post(
        url, {"update_check_email": "test@example.com", "update_check_enabled": "on"}
    )

    assert response.status_code == 302
    assert response.url == url
    gs.settings.flush()
    assert gs.settings.update_check_enabled
    assert gs.settings.update_check_email == "test@example.com"

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


def test_update_check_view_renders_status_badges(client, admin_user):
    client.force_login(admin_user)
    gs = GlobalSettings()
    gs.settings.update_check_enabled = True
    gs.settings.update_check_last = now()
    result = {
        "status": "ok",
        "version": {"latest": "1000.0.0", "yours": "1.0.0", "updatable": False},
        "plugins": {},
    }
    gs.settings.update_check_result = result

    response = client.get(reverse("orga:admin.update"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "fa-check-circle" in content
    assert "fa-arrow-circle-up" not in content

    gs.settings.update_check_result = {
        **result,
        "version": {**result["version"], "updatable": True},
    }

    response = client.get(reverse("orga:admin.update"))

    content = response.content.decode()
    assert "fa-arrow-circle-up" in content
    assert "fa-check-circle" not in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_admin_user_list_search_finds_users(
    client, admin_user, item_count, django_assert_num_queries
):
    client.force_login(admin_user)
    UserFactory.create_batch(item_count, name="SearchUser")

    with django_assert_num_queries(8):
        response = client.get(reverse("orga:admin.user.list"), {"q": "SearchUser"})

    assert response.status_code == 200
    assert "SearchUser" in response.content.decode()


def test_admin_user_list_without_search_and_out_of_range_pages(client, admin_user):
    client.force_login(admin_user)
    UserFactory(name="Ab User")
    url = reverse("orga:admin.user.list")

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ab User" not in content
    assert "Show per page" not in content
    assert 'class="pagination' not in content

    response = client.get(url, {"q": "Ab"})

    assert response.status_code == 200
    assert "Ab User" not in response.content.decode()

    for page in ("0", "9999", "99999999999999999999"):
        response = client.get(url, {"q": "Ab User", "page": page})
        assert response.status_code == 404, page


def test_admin_user_detail_shows_user_data_and_resets_password(
    client, admin_user, make_image
):
    event = EventFactory()
    target = make_orga_user(event)
    picture = ProfilePictureFactory(user=target, avatar=make_image())
    target.name = "Detail User"
    target.email_verification_state = EmailVerificationState.LEGACY
    target.profile_picture = picture
    target.save()
    speaker = SpeakerFactory(user=target, event=event)
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    event_log = ActivityLogFactory(event=event, person=target, content_object=event)
    token_log = make_token_update_log(target)
    client.force_login(admin_user)
    url = reverse("orga:admin.user.detail", kwargs={"code": target.code})

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Detail User" in content
    assert picture.avatar.url in content
    assert submission.title in content
    assert set(response.context["tablist"].keys()) == {
        "teams",
        "submissions",
        "history",
    }
    assert list(response.context["teams"]) == [target.teams.get()]
    assert response.context["history_log_entries"] == [token_log, event_log]
    assert response.context["history_with_objects"] is True
    assert response.context["history_show_event"] is True
    assert reverse("orga:admin.log.detail", kwargs={"pk": token_log.pk}) in content
    assert "Unverified" in content
    assert "Legacy" not in content
    assert (
        reverse("orga:admin.user.verification", kwargs={"code": target.code}) in content
    )

    response = client.post(url)

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.user.list")
    target.refresh_from_db()
    assert target.pw_reset_token is not None


def test_admin_user_detail_renders_pending_email_without_writes(client, admin_user):
    sent = now()
    target = UserFactory(
        email_verification_state=EmailVerificationState.VERIFIED,
        pending_email="pending@example.com",
        pending_email_sent=sent,
    )
    client.force_login(admin_user)
    url = reverse("orga:admin.user.detail", kwargs={"code": target.code})

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "pending@example.com" in content
    assert "awaiting confirmation" in content
    assert "expired" not in content

    expired = sent - dt.timedelta(hours=25)
    User.objects.filter(pk=target.pk).update(pending_email_sent=expired)

    response = client.get(url)

    content = response.content.decode()
    assert "pending@example.com" in content
    assert "expired" in content
    assert "awaiting confirmation" not in content
    target.refresh_from_db()
    assert target.pending_email == "pending@example.com"
    assert target.pending_email_sent == expired
    with scopes_disabled():
        assert list(target.logged_actions()) == []


def test_admin_user_verification_state_changes_gate_next_request(client, admin_user):
    target = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)
    target_client = Client()
    target_client.force_login(target)
    client.force_login(admin_user)
    url = reverse("orga:admin.user.verification", kwargs={"code": target.code})

    for state in ("legacy", "nonsense", ""):
        response = client.post(url, {"state": state}, follow=True)
        assert response.status_code == 200, state
        assert "We had trouble saving your input" in response.content.decode(), state

    target.refresh_from_db()
    assert target.email_verification_state == EmailVerificationState.VERIFIED
    with scopes_disabled():
        logs = target.logged_actions().filter(
            action_type="pretalx.user.email.verification.set"
        )
        assert list(logs) == []

    response = client.post(url, {"state": "unverified"})

    assert response.status_code == 302
    assert response.url == reverse(
        "orga:admin.user.detail", kwargs={"code": target.code}
    )
    target.refresh_from_db()
    assert target.email_verification_state == EmailVerificationState.UNVERIFIED
    with scopes_disabled():
        log = logs.get()
    assert log.person == admin_user
    assert log.data == {"state": "unverified"}
    response = target_client.get(reverse("orga:user.view"))
    assert response.status_code == 302
    assert response.url == reverse("orga:auth.verification")

    response = client.post(url, {"state": "verified"})

    assert response.status_code == 302
    target.refresh_from_db()
    assert target.email_verification_state == EmailVerificationState.VERIFIED
    with scopes_disabled():
        assert [log.data for log in logs.order_by("timestamp")] == [
            {"state": "unverified"},
            {"state": "verified"},
        ]
    assert target_client.get(reverse("orga:user.view")).status_code == 200


def test_admin_user_delete_shreds_or_deactivates(client, admin_user):
    plain = UserFactory()
    plain_pk = plain.pk
    event = EventFactory()
    orga_user = make_orga_user(event)
    orga_client = Client()
    orga_client.force_login(orga_user)
    assert orga_client.get(reverse("orga:user.view")).status_code == 200
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": plain.code})
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.user.list")
    assert not User.objects.filter(pk=plain_pk).exists()

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": orga_user.code})
    )

    assert response.status_code == 302
    orga_user.refresh_from_db()
    assert not orga_user.is_active
    response = orga_client.get(reverse("orga:user.view"))
    assert response.status_code == 302
    assert response.url.startswith(settings.LOGIN_URL)


def test_admin_log_detail_shows_changes_and_skips_event_entries(client, admin_user):
    target = UserFactory()
    log = make_token_update_log(target)
    with scopes_disabled():
        alpha, beta = log.content_object.limit_events.order_by("name")
    event_log = EventFactory().log_action(
        "pretalx.event.update",
        person=admin_user,
        old_data={"name": "Old event name"},
        new_data={"name": "New event name"},
    )
    client.force_login(admin_user)

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
    assert f"[{alpha.pk}, {beta.pk}]" not in content

    response = client.get(reverse("orga:admin.log.detail", kwargs={"pk": event_log.pk}))

    assert response.status_code == 404


def test_healthcheck_returns_200(client):
    response = client.get("/healthcheck/")

    assert response.status_code == 200
    assert response.content == b""


@override_settings(
    CACHES={
        **settings.CACHES,
        "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
    }
)
def test_healthcheck_returns_503_when_cache_unavailable(client):
    response = client.get("/healthcheck/")

    assert response.status_code == 503
    assert b"Cache not available" in response.content
