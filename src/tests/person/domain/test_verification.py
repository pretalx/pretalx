# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import time

import pytest
from django.core import mail as djmail
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from pretalx.common.domain.queries.log import actions_by
from pretalx.common.urls import build_absolute_uri
from pretalx.person.domain.verification import (
    KIND_CHANGE,
    KIND_VERIFY,
    SEND_COOLDOWN,
    VERIFICATION_SALT,
    AlreadyVerifiedError,
    ExpiredVerificationTokenError,
    InvalidVerificationTokenError,
    PendingEmailExpiredError,
    PendingEmailTakenError,
    SendCooldownError,
    VerificationError,
    cancel_email_change,
    check_send_cooldown,
    confirm_verification,
    correct_unverified_email,
    finalize_registration,
    get_verification_url,
    make_verification_token,
    parse_verification_token,
    pending_email_expired,
    promote_on_invitation_match,
    request_email_change,
    send_cooldown_remaining,
    send_verification_mail,
    set_verification_state,
)
from pretalx.person.enums import EmailVerificationState
from tests.factories import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _log_entries(user, action_type):
    return list(actions_by(user).filter(action_type=action_type))


@pytest.mark.parametrize("kind", (KIND_VERIFY, KIND_CHANGE))
def test_verification_token_round_trip_without_addresses(kind):
    user = UserFactory(email="secret-address@example.com")
    user.pending_email = "secret-pending@example.com"
    user.pending_email_sent = now()
    user.save()

    token = make_verification_token(user, kind)

    assert parse_verification_token(token) == (user, kind)
    assert "secret-address" not in token
    assert "secret-pending" not in token
    payload = signing.loads(token, salt=VERIFICATION_SALT)
    assert set(payload.keys()) == {"user", "kind", "check"}
    assert "secret-address" not in str(payload.values())
    assert "secret-pending" not in str(payload.values())


def test_change_kind_requires_pending_email():
    user = UserFactory()
    djmail.outbox = []

    with pytest.raises(ValueError, match="pending"):
        make_verification_token(user, KIND_CHANGE)
    with pytest.raises(ValueError, match="pending"):
        send_verification_mail(user, KIND_CHANGE)

    assert djmail.outbox == []


def test_parse_verification_token_rejects_garbage_and_expired_tokens():
    user = UserFactory()
    real_time = time.time()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(time, "time", lambda: real_time - 25 * 3600)
        expired = make_verification_token(user, KIND_VERIFY)

    with pytest.raises(InvalidVerificationTokenError):
        parse_verification_token("garbage-token")
    with pytest.raises(ExpiredVerificationTokenError):
        parse_verification_token(expired)


@pytest.mark.parametrize(
    "payload",
    ({"user": "NONEXIST"}, {"kind": "bogus"}),
    ids=["unknown_user", "unknown_kind"],
)
def test_parse_verification_token_rejects_unknown_user_or_kind(payload):
    user = UserFactory()
    token = signing.dumps(
        {"user": user.code, "kind": KIND_VERIFY, "check": "0" * 16} | payload,
        salt=VERIFICATION_SALT,
    )

    with pytest.raises(InvalidVerificationTokenError):
        parse_verification_token(token)


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    (
        (KIND_VERIFY, "email", "after@example.com"),
        (KIND_CHANGE, "pending_email", "second@example.com"),
    ),
    ids=["email_change", "pending_change"],
)
def test_parse_verification_token_rejects_stale_token(kind, field, value):
    user = UserFactory(email="before@example.com")
    user.pending_email = "first@example.com"
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, kind)

    setattr(user, field, value)
    user.save()

    with pytest.raises(InvalidVerificationTokenError):
        parse_verification_token(token)


@pytest.mark.parametrize(
    ("use_event", "orga", "expected_urlname"),
    (
        (True, False, "cfp:event.verify"),
        (True, True, "orga:event.auth.verify"),
        (False, False, "orga:auth.verify"),
    ),
    ids=["cfp_with_event", "orga_with_event", "without_event"],
)
def test_get_verification_url(use_event, orga, expected_urlname, event):
    kwargs = {"event": event, "orga": orga} if use_event else {"orga": orga}
    url = get_verification_url("sometoken", **kwargs)

    expected_kwargs = {"token": "sometoken"}
    if use_event:
        expected_kwargs["event"] = event.slug
    assert url == build_absolute_uri(expected_urlname, kwargs=expected_kwargs)


def test_send_verification_mail_verify_kind(event):
    user = UserFactory()
    djmail.outbox = []

    send_verification_mail(user, KIND_VERIFY, event=event)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert f"/{event.slug}/verify/" in djmail.outbox[0].body
    actions = _log_entries(user, "pretalx.user.email.verification.send")
    assert len(actions) == 1
    assert actions[0].data == {"email": user.email, "kind": KIND_VERIFY}
    assert send_cooldown_remaining(user) == SEND_COOLDOWN.total_seconds()


def test_send_verification_mail_change_kind_goes_to_pending_address():
    user = UserFactory()
    user.pending_email = "pending@example.com"
    user.pending_email_sent = now()
    user.save()
    djmail.outbox = []

    send_verification_mail(user, KIND_CHANGE)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["pending@example.com"]
    assert "/orga/verify/" in djmail.outbox[0].body
    actions = _log_entries(user, "pretalx.user.email.verification.send")
    assert actions[0].data == {"email": "pending@example.com", "kind": KIND_CHANGE}


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    ((None, 0), (150, 150), (400, 0)),
    ids=["never_sent", "mid_cooldown", "clamped_to_zero"],
)
def test_send_cooldown_remaining(elapsed, expected):
    user = UserFactory()
    if elapsed is not None:
        cache.set(
            f"pretalx_email_verification_cooldown_{user.pk}",
            now().timestamp() - elapsed,
            timeout=300,
        )

    assert send_cooldown_remaining(user) == expected


def test_confirm_verification_verify_kind_sets_verified_once():
    user = UserFactory(email_verification_state=EmailVerificationState.UNVERIFIED)
    token = make_verification_token(user, KIND_VERIFY)

    result = confirm_verification(token)

    user.refresh_from_db()
    assert result == (user, KIND_VERIFY)
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    actions = _log_entries(user, "pretalx.user.email.verification.confirm")
    assert len(actions) == 1
    assert actions[0].data == {"email": user.email}

    with pytest.raises(AlreadyVerifiedError):
        confirm_verification(token)

    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    assert len(_log_entries(user, "pretalx.user.email.verification.confirm")) == 1


@pytest.mark.parametrize(
    "state",
    (EmailVerificationState.VERIFIED, EmailVerificationState.LEGACY),
    ids=["verified", "legacy"],
)
def test_confirm_verification_change_kind_applies_pending_change(state):
    user = UserFactory(email="old@example.com")
    user.email_verification_state = state
    user.pending_email = "new@example.com"
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, KIND_CHANGE)
    djmail.outbox = []

    result = confirm_verification(token)

    user.refresh_from_db()
    assert result == (user, KIND_CHANGE)
    assert user.email == "new@example.com"
    assert user.pending_email is None
    assert user.pending_email_sent is None
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["old@example.com"]
    actions = _log_entries(user, "pretalx.user.email.change.confirm")
    assert len(actions) == 1
    assert actions[0].data == {
        "old_email": "old@example.com",
        "new_email": "new@example.com",
    }


def test_confirm_verification_change_kind_expired_pending_clears():
    user = UserFactory(email_verification_state=EmailVerificationState.UNVERIFIED)
    user.pending_email = "new@example.com"
    user.pending_email_sent = now() - dt.timedelta(hours=25)
    user.save()
    token = make_verification_token(user, KIND_CHANGE)

    with pytest.raises(PendingEmailExpiredError):
        confirm_verification(token)

    user.refresh_from_db()
    assert user.pending_email is None
    assert user.pending_email_sent is None
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED


def test_confirm_verification_change_kind_target_taken_clears_pending_and_logs():
    user = UserFactory(
        email="old@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    user.pending_email = "new@example.com"
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, KIND_CHANGE)
    UserFactory(email="new@example.com")
    djmail.outbox = []

    with pytest.raises(PendingEmailTakenError):
        confirm_verification(token)

    user.refresh_from_db()
    assert user.email == "old@example.com"
    assert user.pending_email is None
    assert user.pending_email_sent is None
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert djmail.outbox == []
    actions = _log_entries(user, "pretalx.user.email.change.taken")
    assert len(actions) == 1
    assert actions[0].data == {"pending_email": "new@example.com"}


def test_request_email_change_sets_pending_and_sends_both_mails(event):
    user = UserFactory(email="current@example.com")
    djmail.outbox = []

    request_email_change(user, "Target@Example.COM", event=event)

    user.refresh_from_db()
    assert user.pending_email == "target@example.com"
    assert user.pending_email_sent is not None
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ["target@example.com"]
    assert f"/{event.slug}/verify/" in djmail.outbox[0].body
    assert djmail.outbox[1].to == ["current@example.com"]
    assert "target@example.com" in djmail.outbox[1].body
    actions = _log_entries(user, "pretalx.user.email.change.request")
    assert len(actions) == 1
    assert actions[0].data == {"pending_email": "target@example.com"}


def test_request_email_change_rejects_taken_address():
    user = UserFactory()
    UserFactory(email="taken@example.com")
    djmail.outbox = []

    with pytest.raises(ValidationError):
        request_email_change(user, "taken@example.com")

    user.refresh_from_db()
    assert user.pending_email is None
    assert djmail.outbox == []


def test_request_email_change_supersede_replaces_pending_and_kills_old_links():
    user = UserFactory()
    request_email_change(user, "first@example.com")
    first_token = make_verification_token(user, KIND_CHANGE)
    first_sent = user.pending_email_sent
    cache.clear()

    request_email_change(user, "second@example.com")

    user.refresh_from_db()
    assert user.pending_email == "second@example.com"
    assert user.pending_email_sent > first_sent
    with pytest.raises(InvalidVerificationTokenError):
        parse_verification_token(first_token)


def test_confirm_verification_change_kind_neutralises_injection_in_email_address():
    user = UserFactory(email="old@example.com")
    user.pending_email = '"<script>alert(1)</script>"@example.com'
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, KIND_CHANGE)
    djmail.outbox = []

    confirm_verification(token)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    html_body = sent.alternatives[0][0]
    assert "<script>" not in html_body
    assert "alert(1)" in html_body  # as escaped text only
    assert "&lt;script&gt;" in html_body
    assert "<script>" not in sent.body


def test_request_email_change_neutralises_injection_in_pending_address():
    user = UserFactory()
    malicious = '"<script>alert(1)</script>"@example.com'
    djmail.outbox = []

    request_email_change(user, malicious)

    notice = djmail.outbox[1]
    html_body = notice.alternatives[0][0]
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body
    assert "<script>" not in notice.body


def test_cancel_email_change_clears_pending_and_logs_only_when_pending():
    user = UserFactory()

    cancel_email_change(user)

    assert _log_entries(user, "pretalx.user.email.change.cancel") == []

    user.pending_email = "pending@example.com"
    user.pending_email_sent = now()
    user.save()

    cancel_email_change(user)

    user.refresh_from_db()
    assert user.pending_email is None
    assert user.pending_email_sent is None
    actions = _log_entries(user, "pretalx.user.email.change.cancel")
    assert len(actions) == 1
    assert actions[0].data == {"pending_email": "pending@example.com"}


@pytest.mark.parametrize(
    ("sent_offset_hours", "expected"),
    ((None, False), (1, False), (25, True)),
    ids=["never_sent", "fresh", "expired"],
)
def test_pending_email_expired(sent_offset_hours, expected):
    user = UserFactory()
    if sent_offset_hours is not None:
        user.pending_email = "pending@example.com"
        user.pending_email_sent = now() - dt.timedelta(hours=sent_offset_hours)
        user.save()

    assert pending_email_expired(user) is expected


def test_correct_unverified_email_replaces_address_once_during_cooldown(event):
    user = UserFactory(
        email="typo@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    old_token = make_verification_token(user, KIND_VERIFY)
    send_verification_mail(user, KIND_VERIFY)
    djmail.outbox = []

    correct_unverified_email(user, "Fixed@Example.COM", event=event)
    with pytest.raises(SendCooldownError):
        correct_unverified_email(user, "second@example.com")

    user.refresh_from_db()
    assert user.email == "fixed@example.com"
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["fixed@example.com"]
    assert f"/{event.slug}/verify/" in djmail.outbox[0].body
    actions = _log_entries(user, "pretalx.user.email.verification.correct")
    assert len(actions) == 1
    assert actions[0].data == {
        "old_email": "typo@example.com",
        "new_email": "fixed@example.com",
    }
    with pytest.raises(InvalidVerificationTokenError):
        parse_verification_token(old_token)


@pytest.mark.parametrize(
    "state", (EmailVerificationState.VERIFIED, EmailVerificationState.LEGACY)
)
def test_correct_unverified_email_requires_unverified_state(state):
    user = UserFactory(email="proven@example.com")
    user.email_verification_state = state
    user.save()
    djmail.outbox = []

    with pytest.raises(VerificationError):
        correct_unverified_email(user, "other@example.com")

    user.refresh_from_db()
    assert user.email == "proven@example.com"
    assert djmail.outbox == []


def test_send_cooldown_blocks_resend_and_grants_one_free_pass():
    user = UserFactory()

    check_send_cooldown(user, free_pass=True)
    send_verification_mail(user, KIND_VERIFY)
    djmail.outbox = []

    with pytest.raises(SendCooldownError) as excinfo:
        send_verification_mail(user, KIND_VERIFY)

    assert excinfo.value.seconds == SEND_COOLDOWN.total_seconds()
    assert "more seconds" in excinfo.value.message
    assert djmail.outbox == []

    check_send_cooldown(user, free_pass=True)
    with pytest.raises(SendCooldownError):
        check_send_cooldown(user, free_pass=True)


def test_correct_unverified_email_rejects_taken_address():
    user = UserFactory(
        email="typo@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    UserFactory(email="taken@example.com")
    djmail.outbox = []

    with pytest.raises(PendingEmailTakenError):
        correct_unverified_email(user, "taken@example.com")

    user.refresh_from_db()
    assert user.email == "typo@example.com"
    assert djmail.outbox == []


def test_finalize_registration_with_matching_invite_promotes_without_mail(event):
    user = UserFactory(
        email="invited@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    djmail.outbox = []

    finalize_registration(user, event=event, invited_email="Invited@Example.COM")

    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    assert djmail.outbox == []
    actions = _log_entries(user, "pretalx.user.email.verification.promote")
    assert len(actions) == 1
    assert actions[0].data == {"email": "invited@example.com"}


def test_finalize_registration_with_mismatched_invite_sends_mail(event):
    user = UserFactory(
        email="other@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    djmail.outbox = []

    finalize_registration(user, event=event, invited_email="invited@example.com")

    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert f"/{event.slug}/verify/" in djmail.outbox[0].body


def test_finalize_registration_without_invite_routes_to_orga_surface():
    user = UserFactory()
    djmail.outbox = []

    finalize_registration(user, orga=True)

    assert len(djmail.outbox) == 1
    assert "/orga/verify/" in djmail.outbox[0].body


@pytest.mark.parametrize(
    ("state", "expected_log"),
    (
        (EmailVerificationState.UNVERIFIED, [{"email": "invited@example.com"}]),
        (EmailVerificationState.LEGACY, [{"email": "invited@example.com"}]),
        (EmailVerificationState.VERIFIED, []),
    ),
    ids=["unverified", "legacy", "already_verified_logs_nothing"],
)
def test_promote_on_invitation_match_promotes(state, expected_log):
    user = UserFactory(email="invited@example.com")
    user.email_verification_state = state
    user.save()

    assert promote_on_invitation_match(user, " Invited@Example.COM ") is True

    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    actions = _log_entries(user, "pretalx.user.email.verification.promote")
    assert [action.data for action in actions] == expected_log


@pytest.mark.parametrize(
    "invited_email",
    (None, "", "someone-else@example.com"),
    ids=["none", "empty", "mismatch"],
)
def test_promote_on_invitation_match_no_match_changes_nothing(invited_email):
    user = UserFactory(
        email="account@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )

    assert promote_on_invitation_match(user, invited_email) is False

    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert _log_entries(user, "pretalx.user.email.verification.promote") == []


@pytest.mark.parametrize(
    ("initial", "target", "expected_log"),
    (
        (
            EmailVerificationState.UNVERIFIED,
            EmailVerificationState.VERIFIED,
            [{"state": EmailVerificationState.VERIFIED}],
        ),
        (
            EmailVerificationState.LEGACY,
            EmailVerificationState.VERIFIED,
            [{"state": EmailVerificationState.VERIFIED}],
        ),
        (
            EmailVerificationState.VERIFIED,
            EmailVerificationState.UNVERIFIED,
            [{"state": EmailVerificationState.UNVERIFIED}],
        ),
        (EmailVerificationState.VERIFIED, EmailVerificationState.VERIFIED, []),
    ),
    ids=["promote_unverified", "promote_legacy", "demote_verified", "same_state"],
)
def test_set_verification_state_applies_and_logs_actor(initial, target, expected_log):
    admin = UserFactory(is_administrator=True)
    user = UserFactory(email_verification_state=initial)
    djmail.outbox = []

    set_verification_state(user, target, actor=admin)

    user.refresh_from_db()
    assert user.email_verification_state == target
    actions = list(
        user.logged_actions().filter(action_type="pretalx.user.email.verification.set")
    )
    assert [action.data for action in actions] == expected_log
    assert all(action.person == admin for action in actions)
    assert djmail.outbox == []


@pytest.mark.parametrize("state", (EmailVerificationState.LEGACY, "nonsense"))
def test_set_verification_state_rejects_invalid_states(state):
    admin = UserFactory(is_administrator=True)
    user = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)

    with pytest.raises(ValueError, match="verified or unverified"):
        set_verification_state(user, state, actor=admin)

    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.VERIFIED
