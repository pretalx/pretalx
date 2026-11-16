import base64
import json
import time
from unittest import mock

import pytest

from pretalx.event.domain.plugins import disable_plugin
from pretalx_pretix_sso import oidc

ISSUER = "https://pretix.example.invalid/org"


def _jwt(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def _claims(**overrides):
    claims = {
        "iss": ISSUER,
        "aud": "test-client",
        "exp": time.time() + 60,
        "nonce": "nonce",
        "sub": "CUST1",
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _fetch(claims, userinfo=None, token_status=200, discovery_issuer=ISSUER):
    token = mock.Mock(status_code=token_status)
    token.json.return_value = {"id_token": _jwt(claims), "access_token": "access"}
    info = mock.Mock(status_code=200)
    info.json.return_value = userinfo if userinfo is not None else {"sub": "CUST1"}
    meta = {
        "issuer": discovery_issuer,
        "token_endpoint": f"{ISSUER}/token",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
    }
    with mock.patch.object(oidc, "discovery", return_value=meta), mock.patch.object(
        oidc.requests, "post", return_value=token
    ) as post, mock.patch.object(oidc.requests, "get", return_value=info):
        result = oidc.fetch_userinfo("code", "https://cb", "nonce", "verifier")
    return result, post


def test_valid_token_returns_userinfo_and_uses_client_secret_post():
    userinfo, post = _fetch(_claims(), {"sub": "CUST1", "email": "a@example.invalid"})
    assert userinfo["email"] == "a@example.invalid"
    sent = post.call_args.kwargs
    assert sent["data"]["client_secret"] == "test-secret"
    assert "auth" not in sent  # Basic auth does not reach pretix through its proxy


def test_issuer_with_trailing_slash_is_accepted():
    _fetch(_claims(iss=ISSUER + "/"))


@pytest.mark.parametrize(
    "claims, message",
    [
        (_claims(iss="https://evil.example.invalid/org"), "issuer"),
        (_claims(aud="other-client"), "audience"),
        (_claims(exp=time.time() - 1), "expired"),
        (_claims(nonce="other"), "nonce"),
        (_claims(sub=None), "subject"),
    ],
)
def test_invalid_id_token_is_rejected(claims, message):
    with pytest.raises(oidc.OIDCError, match=message):
        _fetch(claims)


def test_issuer_is_checked_against_config_not_discovery():
    evil = "https://evil.example.invalid/org"
    with pytest.raises(oidc.OIDCError, match="issuer"):
        _fetch(_claims(iss=evil), discovery_issuer=evil)


def test_userinfo_subject_must_match_token():
    with pytest.raises(oidc.OIDCError, match="subject"):
        _fetch(_claims(), {"sub": "SOMEONE-ELSE"})


def test_token_endpoint_error_is_rejected():
    with pytest.raises(oidc.OIDCError, match="400"):
        _fetch(_claims(), token_status=400)


def test_pkce_challenge_matches_verifier():
    import hashlib

    verifier, challenge = oidc.new_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == expected.rstrip(b"=").decode()


def test_environment_overrides_config_file(monkeypatch):
    assert oidc.get_config()["client_secret"] == "test-secret"
    monkeypatch.setenv("PRETALX_PRETIX_SSO_CLIENT_SECRET", "from-env")
    assert oidc.get_config()["client_secret"] == "from-env"


def test_event_map_parsing(settings, monkeypatch):
    monkeypatch.setenv("PRETALX_PRETIX_SSO_EVENT_MAP", "a=b, c = d ,broken")
    assert oidc.get_config()["event_map"] == {"a": "b", "c": "d"}


def test_is_enabled_requires_plugin_on_event(event):
    assert oidc.is_enabled(event)
    disable_plugin(event, "pretalx_pretix_sso")
    assert not oidc.is_enabled(event)


def _token_response(json_value=None, bad_json=False):
    response = mock.Mock(status_code=200)
    if bad_json:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_value
    return response


@pytest.mark.parametrize(
    "token_response",
    [
        _token_response(bad_json=True),
        _token_response(["not", "an", "object"]),
        _token_response({"id_token": 42, "access_token": "a"}),
        _token_response({"id_token": _jwt(["claims", "list"]), "access_token": "a"}),
        _token_response({"id_token": _jwt(_claims(exp="soon")), "access_token": "a"}),
        _token_response({"id_token": _jwt(_claims())}),  # no access token
    ],
)
def test_malformed_token_response_raises_oidc_error(token_response):
    meta = {"issuer": ISSUER, "token_endpoint": "t", "userinfo_endpoint": "u"}
    with mock.patch.object(oidc, "discovery", return_value=meta), mock.patch.object(
        oidc.requests, "post", return_value=token_response
    ), pytest.raises(oidc.OIDCError):
        oidc.fetch_userinfo("code", "https://cb", "nonce", "verifier")


def test_malformed_userinfo_raises_oidc_error():
    token = _token_response({"id_token": _jwt(_claims()), "access_token": "a"})
    meta = {"issuer": ISSUER, "token_endpoint": "t", "userinfo_endpoint": "u"}
    info = mock.Mock(status_code=200)
    info.json.side_effect = ValueError("html error page")
    with mock.patch.object(oidc, "discovery", return_value=meta), mock.patch.object(
        oidc.requests, "post", return_value=token
    ), mock.patch.object(oidc.requests, "get", return_value=info), pytest.raises(
        oidc.OIDCError
    ):
        oidc.fetch_userinfo("code", "https://cb", "nonce", "verifier")


@pytest.mark.parametrize(
    "document", [ValueError("not json"), {"issuer": ISSUER}, ["list"]]
)
def test_broken_discovery_raises_oidc_error_and_is_not_cached(document):
    response = mock.Mock()
    response.raise_for_status = lambda: None
    if isinstance(document, Exception):
        response.json.side_effect = document
    else:
        response.json.return_value = document
    with mock.patch.object(oidc.requests, "get", return_value=response) as get:
        for _ in range(2):
            with pytest.raises(oidc.OIDCError):
                oidc.discovery()
    assert get.call_count == 2


def test_malformed_event_map_entries_are_reported_once(monkeypatch, caplog):
    oidc._parse_event_map.cache_clear()
    monkeypatch.setenv("PRETALX_PRETIX_SSO_EVENT_MAP", "good=pretix-good, broken, =x, y=, ,")
    with caplog.at_level("WARNING", logger="pretalx_pretix_sso.oidc"):
        assert oidc.get_config()["event_map"] == {"good": "pretix-good"}
        oidc.get_config()  # same value again: no repeated warnings
    reported = [r.getMessage() for r in caplog.records]
    assert len(reported) == 3
    assert all("expected pretalx-slug=pretix-slug" in m for m in reported)
    assert any("'broken'" in m for m in reported)


def test_event_map_result_cannot_corrupt_cache(monkeypatch):
    oidc._parse_event_map.cache_clear()
    monkeypatch.setenv("PRETALX_PRETIX_SSO_EVENT_MAP", "a=b")
    oidc.get_config()["event_map"]["a"] = "changed"
    assert oidc.get_config()["event_map"] == {"a": "b"}
