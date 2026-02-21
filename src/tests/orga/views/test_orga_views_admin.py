# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json

import pytest
import responses
from django.core.cache import cache
from django.test import override_settings

from pretalx.common.models.settings import GlobalSettings
from pretalx.person.models import User


@pytest.mark.django_db
def test_admin_user_detail_shows_submissions(administrator_client, speaker, submission):
    response = administrator_client.get(f"/orga/admin/users/{speaker.code}/")
    assert response.status_code == 200
    assert submission.title in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
def test_admin_user_list_num_queries(
    administrator_client, speaker, django_assert_num_queries, item_count
):
    cache.clear()
    if item_count == 2:
        User.objects.create_user(
            email="jane2@speaker.org", password="speakerpwd1!", name="Jane Doe"
        )
    with django_assert_num_queries(6):
        response = administrator_client.get("/orga/admin/users/?q=Jane")
    assert response.status_code == 200
    assert speaker.name in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_admin_dashboard_only_for_admin_user(orga_user, orga_client, is_administrator):
    orga_user.is_administrator = is_administrator
    orga_user.save()
    response = orga_client.get("/orga/admin/")
    assert (response.status_code == 200) is is_administrator
    assert ("Administrator information" in response.text) is is_administrator


@pytest.fixture
def user():
    return User.objects.create_user(email="dummy@dummy.dummy", password="dummy")


def request_callback_updatable(request):
    json_data = json.loads(request.body.decode())
    resp_body = {
        "status": "ok",
        "version": {
            "latest": "1000.0.0",
            "yours": json_data.get("version"),
            "updatable": True,
        },
        "plugins": {},
    }
    return 200, {"Content-Type": "text/json"}, json.dumps(resp_body)


@pytest.mark.django_db
def test_update_notice_displayed(client, user):
    client.login(email="dummy@dummy.dummy", password="dummy")

    r = client.get("/orga/", follow=True)
    assert "pretalx automatically checks for updates in the background" not in r.text

    user.is_administrator = True
    user.save()
    r = client.get("/orga/", follow=True)
    assert "pretalx automatically checks for updates in the background" in r.text

    client.get("/orga/admin/update/")  # Click it
    r = client.get("/orga/", follow=True)
    assert "pretalx automatically checks for updates in the background" not in r.text


@pytest.mark.django_db
def test_settings(client, user):
    user.is_administrator = True
    user.save()
    client.login(email="dummy@dummy.dummy", password="dummy")

    client.post(
        "/orga/admin/update/",
        {"update_check_email": "test@example.com", "update_check_enabled": "on"},
    )
    gs = GlobalSettings()
    gs.settings.flush()
    assert gs.settings.update_check_enabled
    assert gs.settings.update_check_email

    client.post(
        "/orga/admin/update/", {"update_check_email": "", "update_check_enabled": ""}
    )
    gs.settings.flush()
    assert not gs.settings.update_check_enabled
    assert not gs.settings.update_check_email


@pytest.mark.django_db
@responses.activate
def test_trigger(client, user):
    responses.add_callback(
        responses.POST,
        "https://pretalx.com/.update_check/",
        callback=request_callback_updatable,
        content_type="application/json",
    )

    user.is_administrator = True
    user.save()
    client.login(email="dummy@dummy.dummy", password="dummy")

    gs = GlobalSettings()
    assert not gs.settings.update_check_last
    client.post("/orga/admin/update/", {"trigger": "on"})
    gs.settings.flush()
    assert gs.settings.update_check_last


@pytest.mark.django_db
def test_test_mail_requires_admin(client, user):
    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.post("/orga/admin/test-mail/")
    assert response.status_code == 404

    user.is_administrator = True
    user.save()
    response = client.post("/orga/admin/test-mail/")
    assert response.status_code == 302


@pytest.mark.django_db
@override_settings(ADMINS=[])
def test_test_mail_no_admins_configured(client, user):
    user.is_administrator = True
    user.save()
    client.login(email="dummy@dummy.dummy", password="dummy")

    response = client.post("/orga/admin/test-mail/", follow=True)
    assert "No administrator email addresses are configured" in response.text


@pytest.mark.django_db
@override_settings(ADMINS=["admin@example.com"])
def test_test_mail_sends_email(client, user, mailoutbox):
    user.is_administrator = True
    user.save()
    client.login(email="dummy@dummy.dummy", password="dummy")

    response = client.post("/orga/admin/test-mail/", follow=True)
    assert "Test email sent successfully" in response.text
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["admin@example.com"]
    assert "test email" in mailoutbox[0].subject.lower()
