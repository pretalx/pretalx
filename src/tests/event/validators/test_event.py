# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from pretalx.event.validators.event import (
    _resolve_host,
    custom_domain_points_to_site,
    normalize_custom_domain,
    validate_attendee_signup_settings,
    validate_custom_domain,
    validate_event_slug_unique,
    validate_feature_flags,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    "value",
    (
        None,
        {},
        {"signup_domains": []},
        {"signup_domains": ["example.com", "sub.example.org"]},
    ),
    ids=("none", "empty_dict", "empty_list", "valid_domains"),
)
def test_validate_attendee_signup_settings_accepts_valid(value):
    validate_attendee_signup_settings(value)


@pytest.mark.parametrize(
    ("value", "expected_code"),
    (
        (["example.com"], "not_dict"),
        ({"signup_domains": "example.com"}, "domains_not_list"),
    ),
    ids=("not_dict", "domains_not_list"),
)
def test_validate_attendee_signup_settings_rejects_invalid(value, expected_code):
    with pytest.raises(ValidationError) as exc_info:
        validate_attendee_signup_settings(value)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "value",
    (
        None,
        {},
        "not a dict",
        {"attendee_signup": True, "present_multiple_times": False},
        {"attendee_signup": False, "present_multiple_times": True},
        {"attendee_signup": False, "present_multiple_times": False},
    ),
    ids=(
        "none",
        "empty",
        "non_dict_passthrough",
        "only_signup",
        "only_multi_slot",
        "neither",
    ),
)
def test_validate_feature_flags_accepts_compatible_combinations(value):
    validate_feature_flags(value)


def test_validate_feature_flags_rejects_signup_with_multi_slot():
    with pytest.raises(ValidationError) as exc_info:
        validate_feature_flags(
            {"attendee_signup": True, "present_multiple_times": True}
        )

    assert exc_info.value.code == "signup_multi_slot_conflict"


def test_validate_event_slug_unique_raises_on_duplicate():
    EventFactory(slug="dupe")

    with pytest.raises(ValidationError) as exc_info:
        validate_event_slug_unique("dupe")

    assert "slug" in exc_info.value.message_dict


def test_validate_event_slug_unique_case_insensitive():
    EventFactory(slug="myevent")

    with pytest.raises(ValidationError):
        validate_event_slug_unique("MyEvent")


def test_validate_event_slug_unique_allows_same_instance():
    event = EventFactory(slug="myevent")

    validate_event_slug_unique("myevent", exclude_event=event)


@pytest.mark.parametrize("slug", ("", None), ids=("empty", "none"))
def test_validate_event_slug_unique_returns_early_for_falsy(slug):
    validate_event_slug_unique(slug)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("custom.example.org", "https://custom.example.org"),
        ("http://custom.example.org", "https://custom.example.org"),
        ("https://custom.example.org", "https://custom.example.org"),
        ("https://custom.example.org/", "https://custom.example.org"),
        ("HTTPS://Custom.example.org/", "https://custom.example.org"),
        ("", ""),
        (None, None),
    ),
    ids=(
        "bare_domain",
        "http_prefix",
        "https_prefix",
        "trailing_slash",
        "mixed_case",
        "empty",
        "none",
    ),
)
def test_normalize_custom_domain(value, expected):
    assert normalize_custom_domain(value) == expected


@pytest.mark.parametrize("value", ("", None), ids=("empty", "none"))
def test_validate_custom_domain_returns_early_for_falsy(value):
    assert validate_custom_domain(value) == (value, None)


def _dns(table):
    """Build a ``_resolve_host`` side effect from a {host: (canonical, ips)} map.

    We mock at the ``_resolve_host`` seam rather than the stdlib resolver
    call, so the tests pin behaviour ("does this domain point at us")
    rather than the implementation's choice of resolver API.
    """

    def resolve(host):
        if host not in table:
            raise OSError("no such host")
        canonical, ips = table[host]
        return canonical.rstrip(".").lower(), set(ips)

    return resolve


def _patch_dns(table):
    return patch(
        "pretalx.event.validators.event._resolve_host", side_effect=_dns(table)
    )


@override_settings(SITE_HOST="pretalx.example.com")
def test_validate_custom_domain_rejects_site_host():
    with pytest.raises(ValidationError):
        validate_custom_domain("https://pretalx.example.com")


@override_settings(SITE_HOST="pretalx.example.com")
def test_validate_custom_domain_unresolvable_raises():
    with _patch_dns({}), pytest.raises(ValidationError) as exc_info:
        validate_custom_domain("https://custom.example.org")

    assert "name server entry" in str(exc_info.value)


@override_settings(SITE_HOST="pretalx.example.com")
def test_validate_custom_domain_accepts_any_resolving_domain():
    # validate_custom_domain only enforces "resolves at all"; whether it
    # points at us is a soft, non-blocking check (see below).
    table = {"custom.example.org": ("custom.example.org", ["9.9.9.9"])}
    with _patch_dns(table):
        value, resolution = validate_custom_domain("https://custom.example.org")

    assert value == "https://custom.example.org"
    assert resolution == ("custom.example.org", {"9.9.9.9"})


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_reuses_passed_resolution():
    """When the caller passes the custom host resolution (the request path
    does), the organiser-supplied host is not resolved a second time: only
    the operator-controlled site host is looked up."""
    table = {"pretalx.example.com": ("pretalx.example.com", ["1.2.3.4"])}
    with _patch_dns(table) as resolve_host:
        result = custom_domain_points_to_site(
            "https://custom.example.org",
            custom_resolution=("custom.example.org", {"9.9.9.9"}),
        )

    assert result is False
    assert resolve_host.call_args_list == [(("pretalx.example.com",), {})]


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_accepts_direct_ip_match():
    table = {
        "custom.example.org": ("custom.example.org", ["1.2.3.4"]),
        "pretalx.example.com": ("pretalx.example.com", ["1.2.3.4"]),
    }
    with _patch_dns(table):
        assert custom_domain_points_to_site("https://custom.example.org") is True


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_accepts_ipv6_match():
    table = {
        "custom.example.org": ("custom.example.org", ["2001:db8::1"]),
        "pretalx.example.com": ("pretalx.example.com", ["2001:db8::1"]),
    }
    with _patch_dns(table):
        assert custom_domain_points_to_site("https://custom.example.org") is True


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_accepts_shared_cdn_canonical():
    # Disjoint IPs, but both the custom domain and the site collapse to the
    # same canonical name because they are CNAMEd through the same backend.
    table = {
        "custom.example.org": ("backend.cdn.example.net", ["9.9.9.9"]),
        "pretalx.example.com": ("backend.cdn.example.net", ["1.2.3.4"]),
    }
    with _patch_dns(table):
        assert custom_domain_points_to_site("https://custom.example.org") is True


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_false_on_mismatch():
    table = {
        "custom.example.org": ("custom.example.org", ["9.9.9.9"]),
        "pretalx.example.com": ("pretalx.example.com", ["1.2.3.4"]),
    }
    with _patch_dns(table):
        assert custom_domain_points_to_site("https://custom.example.org") is False


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_true_when_site_unresolvable():
    # Cannot resolve our own host (e.g. internal SITE_URL in production):
    # the answer is inconclusive, so we do not warn.
    table = {"custom.example.org": ("custom.example.org", ["9.9.9.9"])}
    with _patch_dns(table):
        assert custom_domain_points_to_site("https://custom.example.org") is True


@override_settings(SITE_HOST="pretalx.example.com")
def test_points_to_site_true_when_custom_unresolvable():
    # Unresolvable custom domains are hard-rejected elsewhere; nothing to
    # warn about here.
    table = {"pretalx.example.com": ("pretalx.example.com", ["1.2.3.4"])}
    with _patch_dns(table):
        assert custom_domain_points_to_site("https://custom.example.org") is True


@pytest.mark.parametrize("value", ("", None), ids=("empty", "none"))
def test_points_to_site_true_for_falsy(value):
    assert custom_domain_points_to_site(value) is True


@override_settings(SITE_HOST="")
def test_points_to_site_true_when_no_site_host():
    # SITE_URL has no hostname (misconfiguration): the answer is
    # inconclusive, so we do not warn (and do not resolve anything).
    with patch("pretalx.event.validators.event._resolve_host") as resolve_host:
        assert custom_domain_points_to_site("https://custom.example.org") is True

    assert not resolve_host.called


def test_resolve_host_follows_canonname_and_collects_ips():
    infos = [
        (None, None, None, "Backend.CDN.example.net.", ("1.2.3.4", 0)),
        (None, None, None, "", ("2001:db8::1", 0, 0, 0)),
    ]
    with patch(
        "pretalx.event.validators.event.socket.getaddrinfo", return_value=infos
    ) as getaddrinfo:
        canonical, ips = _resolve_host("custom.example.org")

    assert canonical == "backend.cdn.example.net"
    assert ips == {"1.2.3.4", "2001:db8::1"}
    assert getaddrinfo.called


def test_resolve_host_falls_back_to_queried_host_without_canonname():
    infos = [(None, None, None, "", ("1.2.3.4", 0))]
    with patch("pretalx.event.validators.event.socket.getaddrinfo", return_value=infos):
        canonical, ips = _resolve_host("Custom.Example.org")

    assert canonical == "custom.example.org"
    assert ips == {"1.2.3.4"}
