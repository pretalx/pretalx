# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import time
from urllib.parse import quote

import pytest
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.core import mail as djmail
from django.test import override_settings
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.person.enums import EmailVerificationState
from pretalx.person.models import User
from pretalx.submission.enums import SubmissionStates
from tests.factories import EventFactory, SubmissionFactory, TrackFactory, UserFactory
from tests.utils import make_orga_user

SessionStore = import_string(f"{settings.SESSION_ENGINE}.SessionStore")

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_login_view_register_sends_verification_mail(client, event):
    url = reverse("cfp:event.login", kwargs={"event": event.slug})
    djmail.outbox = []

    response = client.post(
        url,
        {
            "register_name": "New Speaker",
            "register_email": "fresh@example.com",
            "register_password": "verysecure123!",
            "register_password_repeat": "verysecure123!",
        },
    )

    user = User.objects.get(email="fresh@example.com")
    assert response.status_code == 302
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["fresh@example.com"]
    assert f"/{event.slug}/verify/" in djmail.outbox[0].body


@pytest.mark.parametrize(
    ("verification_state", "extra_data"),
    (
        pytest.param(EmailVerificationState.VERIFIED, {}, id="verified"),
        pytest.param(EmailVerificationState.UNVERIFIED, {}, id="unverified"),
        pytest.param(
            EmailVerificationState.VERIFIED,
            {"register_email": "speaker@example.com"},
            id="autofilled_register_email",
        ),
    ),
)
def test_login_view_successful_login_sends_no_mail(
    client, event, verification_state, extra_data
):
    UserFactory(
        email="speaker@example.com",
        password="testpassword!",
        email_verification_state=verification_state,
    )
    url = reverse("cfp:event.login", kwargs={"event": event.slug})
    djmail.outbox = []

    response = client.post(
        url,
        {"login_email": "speaker@example.com", "login_password": "testpassword!"}
        | extra_data,
    )

    assert response.status_code == 302
    assert event.urls.user_submissions in response.url
    assert djmail.outbox == []
    assert User.objects.filter(email="speaker@example.com").count() == 1


@pytest.mark.parametrize(
    ("verification_state", "stored"),
    (
        (EmailVerificationState.UNVERIFIED, True),
        (EmailVerificationState.VERIFIED, False),
    ),
    ids=["unverified-stores", "verified-does-not-store"],
)
def test_login_view_stores_next_destination_only_for_unverified_users(
    client, event, verification_state, stored
):
    UserFactory(
        email="speaker@example.com",
        password="testpassword!",
        email_verification_state=verification_state,
    )
    destination = f"/{event.slug}/talk/ABCDEF/#signup"
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.post(
        f"{url}?next={quote(destination)}",
        {"login_email": "speaker@example.com", "login_password": "testpassword!"},
    )

    assert response.status_code == 302
    assert response.url == destination
    if stored:
        assert client.session["verification_next"] == destination
    else:
        assert "verification_next" not in client.session


def test_login_view_rejects_wrong_password_and_redirects_logged_in_user(client, event):
    speaker = UserFactory(email="speaker@example.com", password="testpassword!")
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.post(
        url, {"login_email": "speaker@example.com", "login_password": "wrongpassword!"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors

    client.force_login(speaker)
    response = client.get(url)

    assert response.status_code == 302
    assert event.urls.user_submissions in response.url


def test_login_view_404_for_non_event(client):
    event = EventFactory(is_public=False)
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.get(url)

    assert response.status_code == 404


def test_logout_view_post_logs_out(client, event):
    speaker = UserFactory()
    client.force_login(speaker)
    url = reverse("cfp:event.logout", kwargs={"event": event.slug})

    me_url = reverse("cfp:event.user.submissions", kwargs={"event": event.slug})

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/cfp"
    assert client.get(me_url).status_code == 200

    response = client.post(url)

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/cfp"
    assert client.get(me_url).status_code == 302


def test_reset_view_sends_one_reset_mail_per_24h_to_known_addresses(client, event):
    speaker = UserFactory(email="speaker@example.com")
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": event.slug})

    response = client.post(url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    assert djmail.outbox == []

    response = client.post(url, {"login_email": "speaker@example.com"})

    assert response.status_code == 302
    speaker.refresh_from_db()
    token = speaker.pw_reset_token
    assert token is not None
    assert [mail.to for mail in djmail.outbox] == [["speaker@example.com"]]

    response = client.post(url, {"login_email": "speaker@example.com"})

    assert response.status_code == 302
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == token
    assert len(djmail.outbox) == 1


def test_recover_view_sets_new_password_for_valid_token_only(client, event):
    speaker = UserFactory(pw_reset_token="validtoken123", pw_reset_time=now())
    url = reverse(
        "cfp:event.recover", kwargs={"event": event.slug, "token": "validtoken123"}
    )

    response = client.get(
        reverse("cfp:event.recover", kwargs={"event": event.slug, "token": "bogus"})
    )

    assert response.status_code == 302
    assert "reset" in response.url

    response = client.post(
        url,
        {"password": "newsecurepassword1!", "password_repeat": "differentpassword1!"},
    )

    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == "validtoken123"

    response = client.post(
        url,
        {"password": "newsecurepassword1!", "password_repeat": "newsecurepassword1!"},
    )

    assert response.status_code == 302
    assert "login" in response.url
    speaker.refresh_from_db()
    assert speaker.pw_reset_token is None
    assert speaker.check_password("newsecurepassword1!")


def test_event_auth_post_rejects_unknown_and_foreign_sessions(client, event):
    url = reverse("cfp:event.auth", kwargs={"event": event.slug})

    response = client.post(url, {"session": "invalidsessionkey"})

    assert response.status_code == 403

    other_event = EventFactory()
    parent_store = SessionStore()
    parent_store[f"child_session_{other_event.pk}"] = "someotherchildkey"
    parent_store.create()

    key = f"pretalx_event_access_{event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    response = client.post(url, {"session": child_store.session_key})

    assert response.status_code == 403
    assert key not in client.session


@pytest.mark.parametrize(
    ("target", "expected_url"),
    (
        ({}, lambda event: event.urls.base),
        ({"target": "cfp"}, lambda event: event.cfp.urls.public),
        ({"target": "schedule"}, lambda event: event.urls.schedule),
        ({"target": "wip_schedule"}, lambda event: f"{event.urls.schedule}v/wip/"),
        ({"target": "unknown"}, lambda event: event.urls.base),
    ),
    ids=["no_target", "cfp", "schedule", "wip_schedule", "unknown"],
)
def test_event_auth_post_target_redirects_correctly(
    client, event, target, expected_url
):
    parent_store = SessionStore()
    parent_store.create()

    key = f"pretalx_event_access_{event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    parent_store[f"child_session_{event.pk}"] = child_store.session_key
    parent_store.save()

    url = reverse("cfp:event.auth", kwargs={"event": event.slug})
    response = client.post(url, {"session": child_store.session_key} | target)

    assert response.status_code == 302
    assert response.url == expected_url(event)
    assert client.session[key] == parent_store.session_key


def _authenticate_on_custom_domain(client, event, user):
    parent_store = SessionStore()
    parent_store[SESSION_KEY] = str(user.pk)
    parent_store[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    parent_store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    parent_store["pretalx_auth_login_time"] = int(time.time())
    parent_store["pretalx_auth_last_used"] = int(time.time())
    parent_store.create()

    child_store = SessionStore()
    child_store[f"pretalx_event_access_{event.pk}"] = parent_store.session_key
    child_store.create()

    parent_store[f"child_session_{event.pk}"] = child_store.session_key
    parent_store.save()

    url = reverse("cfp:event.auth", kwargs={"event": event.slug})
    client.post(url, {"session": child_store.session_key})
    return parent_store


def test_event_access_does_not_expose_proposals_to_reviewer(client, event):
    with scopes_disabled():
        reviewer_track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        reviewer = make_orga_user(
            event, can_change_submissions=False, is_reviewer=True, all_events=True
        )
        team = reviewer.teams.first()
        team.limit_tracks.add(reviewer_track)
        submission = SubmissionFactory(
            event=event, track=other_track, state=SubmissionStates.SUBMITTED
        )
        url = submission.urls.public

    _authenticate_on_custom_domain(client, event, reviewer)

    with scopes_disabled():
        assert client.get(event.wip_schedule.urls.public).status_code == 200
    assert client.get(url).status_code == 404


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
@pytest.mark.parametrize("invalidation", ("team", "password", "idle_timeout"))
def test_event_access_ends_when_granting_session_becomes_invalid(
    client, event, invalidation
):
    with scopes_disabled():
        organiser = make_orga_user(event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        url = submission.urls.public
        widget_url = event.wip_schedule.urls.widget_data

    parent_store = _authenticate_on_custom_domain(client, event, organiser)

    assert client.get(url).status_code == 200
    assert client.get(widget_url).status_code == 200

    with scopes_disabled():
        if invalidation == "team":
            organiser.teams.first().members.remove(organiser)
        elif invalidation == "password":
            organiser.set_password("a new and different password")
            organiser.save()
        else:
            parent_store["pretalx_auth_last_used"] = int(time.time()) - 200
            parent_store.save()

    assert client.get(url).status_code == 404
    assert client.get(widget_url).status_code == 404
    assert SESSION_KEY in SessionStore(parent_store.session_key).load()


@pytest.mark.parametrize("logged_in_as", ("granting_user", "other_user"))
def test_event_access_yields_to_logged_in_user(client, event, logged_in_as):
    with scopes_disabled():
        organiser = make_orga_user(event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        url = submission.urls.public

    _authenticate_on_custom_domain(client, event, organiser)
    user = organiser if logged_in_as == "granting_user" else UserFactory()
    client.force_login(user)

    expected = 200 if logged_in_as == "granting_user" else 404
    assert client.get(url).status_code == expected


def test_event_access_is_limited_to_the_preview_pages(
    client, public_event_with_schedule
):
    event = public_event_with_schedule
    event.is_public = False
    event.save()
    with scopes_disabled():
        organiser = make_orga_user(event)
        widget_url = event.wip_schedule.urls.widget_data
        changelog_url = event.urls.changelog

    _authenticate_on_custom_domain(client, event, organiser)

    assert client.get(widget_url).status_code == 200
    assert client.get(changelog_url).status_code == 404

    client.force_login(organiser)

    assert client.get(changelog_url).status_code == 200
