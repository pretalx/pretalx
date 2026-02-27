import json

import pytest
import responses
from django.core import mail as djmail
from django.test import override_settings
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.models.settings import GlobalSettings
from pretalx.person.models import User
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_user():
    return UserFactory(is_administrator=True)


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_admin_dashboard_requires_administrator(client, is_administrator):
    """Only administrators can access the admin dashboard."""
    user = UserFactory(is_administrator=is_administrator)
    client.force_login(user)

    response = client.get(reverse("orga:admin.dashboard"))

    if is_administrator:
        assert response.status_code == 200
        assert "Administrator information" in response.content.decode()
    else:
        assert response.status_code == 404


@pytest.mark.django_db
def test_admin_dashboard_anonymous_user_redirects_to_login(client):
    """Anonymous users are redirected to login."""
    response = client.get(reverse("orga:admin.dashboard"))

    assert response.status_code == 302
    assert "/orga/login/" in response.url


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_test_mail_requires_administrator(client, is_administrator):
    """Only administrators can send test mails."""
    user = UserFactory(is_administrator=is_administrator)
    client.force_login(user)

    response = client.post(reverse("orga:admin.test_mail"))

    if is_administrator:
        assert response.status_code == 302
    else:
        assert response.status_code == 404


@pytest.mark.django_db
@override_settings(ADMINS=[])
def test_test_mail_no_admins_configured(client, admin_user):
    """Test mail shows error when no admin emails are configured."""
    client.force_login(admin_user)

    response = client.post(reverse("orga:admin.test_mail"), follow=True)

    assert (
        "No administrator email addresses are configured" in response.content.decode()
    )


@pytest.mark.django_db
@override_settings(ADMINS=["admin@example.com"])
def test_test_mail_sends_email(client, admin_user):
    """Test mail sends to configured admin addresses and shows success."""
    client.force_login(admin_user)
    djmail.outbox = []

    response = client.post(reverse("orga:admin.test_mail"), follow=True)

    content = response.content.decode()
    assert "Test email sent successfully" in content
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "test email" in djmail.outbox[0].subject.lower()


@pytest.mark.django_db
@override_settings(
    ADMINS=["admin@example.com"],
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="invalid.host.example",
    EMAIL_PORT=9999,
    EMAIL_TIMEOUT=1,
)
def test_test_mail_smtp_error_shows_failure(client, admin_user):
    """SMTP errors are caught and displayed as error messages."""
    client.force_login(admin_user)

    response = client.post(reverse("orga:admin.test_mail"), follow=True)

    assert "Failed to send test email" in response.content.decode()


@pytest.mark.django_db
@override_settings(ADMINS=["admin@example.com"])
def test_test_mail_redirects_to_dashboard(client, admin_user):
    """Test mail POST redirects back to admin dashboard."""
    client.force_login(admin_user)

    response = client.post(reverse("orga:admin.test_mail"))

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.dashboard")


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_update_check_view_requires_administrator(client, is_administrator):
    """Only administrators can access the update check view."""
    user = UserFactory(is_administrator=is_administrator)
    client.force_login(user)

    response = client.get(reverse("orga:admin.update"))

    if is_administrator:
        assert response.status_code == 200
    else:
        assert response.status_code == 404


@pytest.mark.django_db
def test_update_check_view_sets_ack(client, admin_user):
    """Visiting the update check page persists update_check_ack=True so the
    'update check active' banner on the orga dashboard disappears."""
    client.force_login(admin_user)
    gs = GlobalSettings()
    assert not gs.settings.update_check_ack

    client.get(reverse("orga:admin.update"))

    gs.settings.flush()
    assert gs.settings.update_check_ack


@pytest.mark.django_db
def test_update_check_form_invalid_shows_error(client, admin_user):
    """Posting an invalid email address shows an error message."""
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    response = client.post(
        url, {"update_check_email": "not-an-email", "update_check_enabled": "on"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.django_db
def test_update_check_settings_save(client, admin_user):
    """Posting settings updates GlobalSettings values."""
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    client.post(
        url, {"update_check_email": "test@example.com", "update_check_enabled": "on"}
    )

    gs = GlobalSettings()
    gs.settings.flush()
    assert gs.settings.update_check_enabled
    assert gs.settings.update_check_email == "test@example.com"


@pytest.mark.django_db
def test_update_check_settings_disable(client, admin_user):
    """Posting with empty values disables update check."""
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


def _update_check_callback(request):
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
@responses.activate
def test_update_check_trigger(client, admin_user):
    """Posting with 'trigger' key runs the update check task."""
    responses.add_callback(
        responses.POST,
        "https://pretalx.com/.update_check/",
        callback=_update_check_callback,
        content_type="application/json",
    )
    client.force_login(admin_user)
    url = reverse("orga:admin.update")

    gs = GlobalSettings()
    assert not gs.settings.update_check_last

    client.post(url, {"trigger": "on"})

    gs.settings.flush()
    assert gs.settings.update_check_last


@pytest.mark.django_db
def test_update_check_trigger_redirects(client, admin_user):
    """Trigger POST redirects back to the update check page."""
    client.force_login(admin_user)

    response = client.post(reverse("orga:admin.update"), {"trigger": "on"})

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.update")


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_admin_user_list_requires_administrator(client, is_administrator):
    """Only administrators can access the user list."""
    user = UserFactory(is_administrator=is_administrator)
    client.force_login(user)

    response = client.get(reverse("orga:admin.user.list"))

    if is_administrator:
        assert response.status_code == 200
    else:
        assert response.status_code == 404


@pytest.mark.django_db
def test_admin_user_list_search_finds_users(client, admin_user):
    """User list search filters by name."""
    client.force_login(admin_user)
    target = UserFactory(name="Findable User")

    response = client.get(reverse("orga:admin.user.list"), {"q": "Findable"})

    assert response.status_code == 200
    assert target.name in response.content.decode()


@pytest.mark.django_db
def test_admin_user_list_empty_without_search(client, admin_user):
    """User list without search query shows no users."""
    client.force_login(admin_user)
    UserFactory(name="Some User")

    response = client.get(reverse("orga:admin.user.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Some User" not in content


@pytest.mark.django_db
def test_admin_user_list_short_search_returns_empty(client, admin_user):
    """User list with search query shorter than 3 chars returns empty results."""
    client.force_login(admin_user)
    UserFactory(name="Ab User")

    response = client.get(reverse("orga:admin.user.list"), {"q": "Ab"})

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ab User" not in content


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.usefixtures("locmem_cache")
def test_admin_user_list_query_count(
    client, admin_user, item_count, django_assert_num_queries
):
    """Query count is constant regardless of user count."""
    client.force_login(admin_user)
    for i in range(item_count):
        UserFactory(name=f"SearchUser{i}")

    with django_assert_num_queries(6):
        response = client.get(reverse("orga:admin.user.list"), {"q": "SearchUser"})

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_admin_user_detail_requires_administrator(client, is_administrator):
    """Only administrators can access user detail."""
    user = UserFactory(is_administrator=is_administrator)
    target = UserFactory()
    client.force_login(user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    if is_administrator:
        assert response.status_code == 200
    else:
        assert response.status_code == 404


@pytest.mark.django_db
def test_admin_user_detail_shows_user_data(client, admin_user):
    """User detail page displays user information."""
    target = UserFactory(name="Detail User", email="detail@example.com")
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert target.name in content


@pytest.mark.django_db
def test_admin_user_detail_shows_submissions(client, admin_user):
    """User detail page shows submissions linked to the user."""
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


@pytest.mark.django_db
def test_admin_user_detail_shows_teams(client, admin_user):
    """User detail page shows teams the user belongs to."""
    event = EventFactory()
    target = make_orga_user(event)
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    assert "teams" in response.context
    assert len(response.context["teams"]) == 1


@pytest.mark.django_db
def test_admin_user_detail_context_has_tablist(client, admin_user):
    """User detail page context includes tablist with expected keys."""
    target = UserFactory()
    client.force_login(admin_user)

    response = client.get(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 200
    assert set(response.context["tablist"].keys()) == {
        "teams",
        "submissions",
        "actions",
    }


@pytest.mark.django_db
def test_admin_user_reset_password(client, admin_user):
    """POST to user detail triggers a password reset."""
    target = UserFactory()
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.detail", kwargs={"code": target.code})
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.user.list")
    target.refresh_from_db()
    assert target.pw_reset_token is not None


@pytest.mark.django_db
def test_admin_user_delete_shreds_user(client, admin_user):
    """Deleting a user with no blocking references shreds them entirely."""
    target = UserFactory()
    target_pk = target.pk
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": target.code})
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:admin.user.list")
    assert not User.objects.filter(pk=target_pk).exists()


@pytest.mark.django_db
def test_admin_user_delete_deactivates_when_shred_fails(client, admin_user):
    """When shred raises UserDeletionError, the user is deactivated instead."""
    event = EventFactory()
    target = make_orga_user(event)
    client.force_login(admin_user)

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": target.code})
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert not target.is_active


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_admin_user_delete_requires_administrator(client, is_administrator):
    """Only administrators can delete users."""
    user = UserFactory(is_administrator=is_administrator)
    target = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("orga:admin.user.delete", kwargs={"code": target.code})
    )

    if is_administrator:
        assert response.status_code == 302
    else:
        assert response.status_code == 404


@pytest.mark.django_db
def test_healthcheck_returns_200(client, locmem_cache):
    """Healthcheck returns 200 when DB and cache are available."""
    response = client.get("/healthcheck/")

    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.django_db
def test_healthcheck_returns_503_when_cache_unavailable(client):
    """Healthcheck returns 503 when cache cannot store values.

    The default DummyCache backend does not actually store values,
    so get() always returns None — triggering the 503 path."""
    response = client.get("/healthcheck/")

    assert response.status_code == 503
    assert b"Cache not available" in response.content
