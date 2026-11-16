from unittest import mock

import pytest
from django.db import IntegrityError
from django.http import Http404

from conftest import _prepare
from pretalx.event.domain.plugins import disable_plugin
from pretalx.person.models import User
from pretalx_pretix_sso import views
from pretalx_pretix_sso.models import PretixCustomer


def _userinfo(sub="CUST1", email="new@example.invalid", verified=True, **extra):
    info = {"sub": sub, "email": email, **extra}
    if verified is not None:
        info["email_verified"] = verified
    return info


def test_redirect_uri_comes_from_site_url_not_request():
    assert views._redirect_uri() == "https://pretalx.example.invalid/p/pretix-sso/callback/"


def test_new_user_is_created_linked_and_logged_in(sso_callback, event):
    response, request = sso_callback(_userinfo(name="New Person"))
    user = User.objects.get(email="new@example.invalid")
    assert request.user == user
    assert user.name == "New Person"
    assert not user.has_usable_password()
    # pretalx gives passwordless accounts an invitation reset token; SSO ones get none
    assert user.pw_reset_token is None
    assert PretixCustomer.objects.get(user=user).identifier == "CUST1"
    assert response.url == event.urls.user_submissions
    # the token exchange used the configured redirect URI
    assert request.fetch.call_args.args[1] == views._redirect_uri()


@pytest.mark.parametrize("verified", [None, False])
def test_unverified_email_is_refused(sso_callback, verified):
    _, request = sso_callback(_userinfo(verified=verified))
    assert not request.user.is_authenticated
    assert not User.objects.filter(email="new@example.invalid").exists()


def test_linked_account_survives_pretix_email_change(sso_callback):
    sso_callback(_userinfo())
    user = User.objects.get(email="new@example.invalid")
    _, request = sso_callback(_userinfo(email="changed@example.invalid"))
    assert request.user == user
    assert not User.objects.filter(email="changed@example.invalid").exists()


def test_first_link_by_email_disables_existing_password(sso_callback, make_speaker):
    squatter = make_speaker("victim@example.invalid", password="attacker-knows-this")
    _, request = sso_callback(_userinfo(sub="V1", email="victim@example.invalid"))
    squatter.refresh_from_db()
    assert request.user == squatter
    assert not squatter.has_usable_password()
    assert PretixCustomer.objects.get(user=squatter).identifier == "V1"


def test_password_set_after_linking_is_kept(sso_callback, make_speaker):
    speaker = make_speaker("victim@example.invalid", password="old")
    sso_callback(_userinfo(sub="V1", email="victim@example.invalid"))
    speaker.set_password("reset-by-owner")
    speaker.save()
    sso_callback(_userinfo(sub="V1", email="victim@example.invalid"))
    speaker.refresh_from_db()
    assert speaker.check_password("reset-by-owner")


def test_organiser_is_refused_and_untouched(sso_callback, admin):
    _, request = sso_callback(_userinfo(sub="ADM", email=admin.email))
    admin.refresh_from_db()
    assert not request.user.is_authenticated
    assert admin.check_password("admin-pw")
    assert not PretixCustomer.objects.filter(identifier="ADM").exists()


def test_team_member_is_refused(sso_callback, event, make_speaker):
    from pretalx.event.models import Team

    reviewer = make_speaker("reviewer@example.invalid")
    team = Team.objects.create(organiser=event.organiser, name="Reviewers", is_reviewer=True)
    team.members.add(reviewer)
    _, request = sso_callback(_userinfo(email="reviewer@example.invalid"))
    assert not request.user.is_authenticated


def test_deactivated_user_is_refused(sso_callback, make_speaker):
    speaker = make_speaker("gone@example.invalid")
    speaker.is_active = False
    speaker.save()
    _, request = sso_callback(_userinfo(email="gone@example.invalid"))
    assert not request.user.is_authenticated


def test_concurrent_creation_reuses_the_other_account(sso_callback):
    # The other request committed the user; our lookup ran just before that
    other = User.objects.create_user(email="new@example.invalid", password=None, name="Other")
    real_filter = User.objects.filter
    calls = []

    def first_lookup_misses(*args, **kwargs):
        calls.append(1)
        return User.objects.none() if len(calls) == 1 else real_filter(*args, **kwargs)

    with mock.patch.object(User.objects, "filter", side_effect=first_lookup_misses):
        _, request = sso_callback(_userinfo())
    assert request.user == other
    assert User.objects.filter(email="new@example.invalid").count() == 1


def test_integrity_error_without_existing_user_is_raised(sso_callback):
    with mock.patch.object(
        User.objects, "create_user", side_effect=IntegrityError("other constraint")
    ), pytest.raises(IntegrityError):
        sso_callback(_userinfo())


def test_state_mismatch_is_refused(sso_callback):
    _, request = sso_callback(_userinfo(), state="forged")
    assert not request.user.is_authenticated
    request.fetch.assert_not_called()


def test_next_url_must_be_local(sso_callback, event):
    response, _ = sso_callback(_userinfo(), next_url="https://evil.example.invalid/")
    assert response.url == event.urls.user_submissions


def test_callback_without_session_is_404(rf):
    from django.contrib.sessions.backends.cache import SessionStore

    request = rf.get("/p/pretix-sso/callback/")
    request.session = SessionStore()
    with pytest.raises(Http404):
        views.CallbackView.as_view()(request)


def test_callback_for_disabled_plugin_is_404(sso_callback, event):
    disable_plugin(event, "pretalx_pretix_sso")
    with pytest.raises(Http404):
        sso_callback(_userinfo())


def test_pretix_error_during_token_exchange_shows_message(event):
    from pretalx_pretix_sso import oidc

    with mock.patch.object(views.oidc, "fetch_userinfo", side_effect=oidc.OIDCError("bad")):
        request = _callback_request(event)
        response = views.CallbackView.as_view()(request)
    assert response.status_code == 302 and response.url == event.urls.login
    assert "failed" in " ".join(str(m) for m in request._messages)


def test_broken_discovery_on_login_start_shows_message(event):
    from django.test import RequestFactory

    from pretalx_pretix_sso import oidc

    request = RequestFactory().get(f"/{event.slug}/p/pretix-sso/login/")
    _prepare(request, event=event)
    with mock.patch.object(views.oidc, "discovery", side_effect=oidc.OIDCError("broken")):
        response = views.LoginStartView.as_view()(request, event=event.slug)
    assert response.status_code == 302 and response.url == event.urls.login
    assert "unavailable" in " ".join(str(m) for m in request._messages)


def test_non_text_email_is_refused(sso_callback):
    _, request = sso_callback({"sub": "X", "email": ["a@example.invalid"], "email_verified": True})
    assert not request.user.is_authenticated


def test_speaker_is_told_when_password_stops_working(sso_callback, make_speaker):
    make_speaker("pw@example.invalid", password="old")
    _, request = sso_callback(_userinfo(sub="P1", email="pw@example.invalid"))
    assert any("previous password" in str(m) for m in request._messages)
    # nothing to say for a speaker without a password
    _, request = sso_callback(_userinfo(sub="P2", email="fresh@example.invalid"))
    assert not any("previous password" in str(m) for m in request._messages)


def _callback_request(event):
    from django.test import RequestFactory

    request = RequestFactory().get("/p/pretix-sso/callback/", {"state": "st", "code": "c"})
    _prepare(request)
    request.session[views.SESSION_KEY] = {
        "state": "st", "nonce": "n", "verifier": "v", "event": event.slug, "next": "",
    }
    return request


def _stale_callback(event_slug, user=None, state_token="tok"):
    from django.test import RequestFactory

    state = f"{state_token}.{event_slug}" if event_slug else state_token
    request = RequestFactory().get("/p/pretix-sso/callback/", {"state": state, "code": "c"})
    _prepare(request, user=user)  # fresh session: no login in progress
    return views.CallbackView.as_view()(request), request


def test_login_start_puts_event_in_state(event):
    from django.test import RequestFactory

    request = RequestFactory().get(f"/{event.slug}/p/pretix-sso/login/")
    _prepare(request, event=event)
    meta = {"authorization_endpoint": "https://pretix.example.invalid/org/oauth2/v1/authorize"}
    with mock.patch.object(views.oidc, "discovery", return_value=meta):
        views.LoginStartView.as_view()(request, event=event.slug)
    token, _, slug = request.session[views.SESSION_KEY]["state"].partition(".")
    assert slug == event.slug and len(token) >= 32


def test_stale_callback_sends_back_to_event_login(event):
    response, request = _stale_callback(event.slug)
    assert response.status_code == 302 and response.url == event.urls.login
    assert "expired" in " ".join(str(m) for m in request._messages)


def test_stale_callback_when_already_logged_in_goes_to_submissions(event, make_speaker):
    speaker = make_speaker("in@example.invalid")
    response, _ = _stale_callback(event.slug, user=speaker)
    assert response.url == event.urls.user_submissions


@pytest.mark.parametrize("slug", ["no-such-event", ""])
def test_stale_callback_without_known_event_is_404(event, slug):
    with pytest.raises(Http404):
        _stale_callback(slug)


def test_stale_callback_for_disabled_plugin_is_404(event):
    disable_plugin(event, "pretalx_pretix_sso")
    with pytest.raises(Http404):
        _stale_callback(event.slug)


def _account_logs(event):
    from pretalx.common.models import ActivityLog

    return list(
        ActivityLog.objects.filter(
            event=event, action_type__startswith="pretalx_pretix_sso.account."
        ).order_by("pk")
    )


def test_new_account_is_logged_once(sso_callback, event):
    sso_callback(_userinfo())
    sso_callback(_userinfo())  # a normal later login is not logged
    logs = _account_logs(event)
    assert [log.action_type for log in logs] == ["pretalx_pretix_sso.account.created"]
    user = User.objects.get(email="new@example.invalid")
    assert logs[0].person == user and logs[0].content_object == user
    assert "created by logging in with pretix" in str(logs[0].display)


def test_first_link_is_logged_with_password_note(sso_callback, event, make_speaker):
    make_speaker("pw@example.invalid", password="old")
    sso_callback(_userinfo(sub="P1", email="pw@example.invalid"))
    (log,) = _account_logs(event)
    assert log.action_type == "pretalx_pretix_sso.account.linked"
    assert log.json_data == {"password_disabled": True}
    assert "password was disabled" in str(log.display)
    # no personal data in the log entry
    assert "pw@example.invalid" not in (log.data or "") and "P1" not in (log.data or "")


def test_moved_link_is_logged(sso_callback, event):
    sso_callback(_userinfo(sub="FIRST"))
    sso_callback(_userinfo(sub="SECOND"))  # same verified email, other pretix account
    assert [log.action_type for log in _account_logs(event)] == [
        "pretalx_pretix_sso.account.created",
        "pretalx_pretix_sso.account.moved",
    ]
    assert "different pretix account" in str(_account_logs(event)[-1].display)
