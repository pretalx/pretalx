from unittest import mock

import pytest

from pretalx_pretix_sso import tickets
from pretalx_pretix_sso.models import PretixCustomer

ITEMS = {"results": [{"id": 1, "admission": True}], "next": None}
ORDERS_PAGE_1 = {
    "results": [
        # add-on/merch only: not a ticket
        {"email": "merch@example.invalid", "customer": "MERCH",
         "positions": [{"item": 99, "attendee_email": None}]},
        # bought for someone else: the attendee holds it, not the buyer
        {"email": "Buyer@example.invalid", "customer": "BUYER",
         "positions": [{"item": 1, "attendee_email": "Friend@example.invalid"}]},
    ],
    "next": "https://pretix.example.invalid/orders/?page=2",
}
ORDERS_PAGE_2 = {
    "results": [
        # no attendee named: the buyer holds it
        {"email": "self@example.invalid", "customer": "SELF",
         "positions": [{"item": 1, "attendee_email": None}, {"item": 99}]},
        # attendee is the buyer: account counts too
        {"email": "named@example.invalid", "customer": "NAMED",
         "positions": [{"item": 1, "attendee_email": "NAMED@example.invalid"}]},
    ],
    "next": None,
}


def _response(data=None, bad_json=False):
    response = mock.Mock()
    response.raise_for_status = lambda: None
    if bad_json:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = data
    return response


def _fake_get(url, params=None, headers=None, timeout=None):
    assert headers == {"Authorization": "Token test-token"}
    if "/items/" in url:
        assert params == {"admission": "true"}
        return _response(ITEMS)
    if "page=2" in url:
        assert params is None  # "next" already carries the query
        return _response(ORDERS_PAGE_2)
    assert params == {
        "status": "p",
        "testmode": "false",
        "include": ["email", "customer", "positions.item", "positions.attendee_email"],
    }
    return _response(ORDERS_PAGE_1)


@pytest.fixture
def holders():
    with mock.patch.object(tickets.requests, "get", side_effect=_fake_get) as get:
        result = tickets._fetch_ticket_holders("test")
    assert get.call_args_list[0].args[0] == (
        "https://pretix.example.invalid/api/v1/organizers/org/events/test/items/"
    )
    return result


def test_only_admission_items_count(holders):
    assert not holders.has_email("merch@example.invalid")
    assert "MERCH" not in holders.customers


def test_named_attendee_holds_ticket_not_buyer(holders):
    assert holders.has_email("friend@example.invalid")
    assert not holders.has_email("buyer@example.invalid")
    assert "BUYER" not in holders.customers


def test_unnamed_ticket_belongs_to_buyer_across_pages(holders):
    assert holders.has_email("self@example.invalid")
    assert "SELF" in holders.customers


def test_attendee_equal_to_buyer_counts_account(holders):
    assert holders.has_email("named@example.invalid")
    assert "NAMED" in holders.customers


@pytest.mark.parametrize("response", [_response(bad_json=True), _response({"detail": "?"})])
def test_malformed_response_raises_lookup_error(response):
    with mock.patch.object(tickets.requests, "get", return_value=response):
        with pytest.raises(tickets.TicketLookupError):
            tickets._fetch_ticket_holders("test")


def test_status_priority(make_speaker):
    linked = make_speaker("linked@example.invalid")
    PretixCustomer.objects.create(user=linked, identifier="CUST1")
    by_email = make_speaker("paid@example.invalid")
    nobody = make_speaker("nobody@example.invalid")
    holders = tickets.TicketHolders.from_emails(
        emails={"paid@example.invalid", "linked@example.invalid"},
        customers={"CUST1"},
    )
    linked.refresh_from_db()
    assert holders.status(linked) == tickets.PAID_ACCOUNT
    assert holders.status(by_email, overridden=True) == tickets.PAID_EMAIL
    assert holders.status(nobody, overridden=True) == tickets.OVERRIDE
    assert holders.status(nobody) is None
    assert tickets.customer_identifier(nobody) is None


def test_cached_until_refresh(event):
    first = tickets.TicketHolders.from_emails({"a@example.invalid"})
    second = tickets.TicketHolders.from_emails({"b@example.invalid"})
    with mock.patch.object(tickets, "_fetch_ticket_holders", side_effect=[first, second]):
        assert tickets.ticket_holders(event) == first
        assert tickets.ticket_holders(event) == first
        assert tickets.ticket_holders(event, refresh=True) == second


def test_event_map_selects_pretix_event(event, monkeypatch):
    assert tickets.pretix_event_slug(event) == "test"
    monkeypatch.setenv("PRETALX_PRETIX_SSO_EVENT_MAP", "test=pretix-test")
    assert tickets.pretix_event_slug(event) == "pretix-test"


def test_organizer_and_base_url_derived_from_issuer():
    conf = tickets.api_config()
    assert conf["base_url"] == "https://pretix.example.invalid"
    assert conf["organizer"] == "org"


def test_cache_holds_only_plain_data(event):
    from django.core.cache import cache

    holders = tickets.TicketHolders.from_emails({"a@example.invalid"}, {"C1"})
    with mock.patch.object(tickets, "_fetch_ticket_holders", return_value=holders):
        tickets.ticket_holders(event)
    key = next(k for k in cache._cache if "pretix_sso_tickets" in k)
    import pickle

    stored = cache._cache[key]
    assert b"@example.invalid" not in stored  # no plain email addresses in Redis
    data = pickle.loads(stored)
    assert data["email_hashes"] == [tickets.email_hash("a@example.invalid")]
    assert data["customers"] == ["C1"]
    assert isinstance(data["fetched_at"], float)
    assert set(data) == {"email_hashes", "customers", "fetched_at"}  # plain data only


@pytest.mark.parametrize("junk", [["unexpected"], {"emails": ["x"]}, "text"])
def test_unreadable_cache_entry_counts_as_miss(event, junk):
    from django.core.cache import cache

    cache.set(f"pretix_sso_tickets:v6:org:{event.slug}", junk)
    fresh = tickets.TicketHolders.from_emails({"fresh@example.invalid"})
    with mock.patch.object(tickets, "_fetch_ticket_holders", return_value=fresh) as fetch:
        assert tickets.ticket_holders(event) == fresh
    fetch.assert_called_once()


def test_cache_outage_does_not_break_lookup(event):
    holders = tickets.TicketHolders.from_emails({"a@example.invalid"})
    with mock.patch.object(tickets.cache, "get", side_effect=ConnectionError("redis down")), \
         mock.patch.object(tickets.cache, "set", side_effect=ConnectionError("redis down")), \
         mock.patch.object(tickets, "_fetch_ticket_holders", return_value=holders):
        assert tickets.ticket_holders(event) == holders


def test_email_hash_is_normalised_and_stable():
    assert tickets.email_hash(" A@Example.Invalid ") == tickets.email_hash("a@example.invalid")
    assert tickets.email_hash("a@example.invalid") != tickets.email_hash("b@example.invalid")
    # fixed across processes and containers: no per-install secret involved
    assert tickets.email_hash("a@example.invalid") == (
        __import__("hashlib").sha256(b"pretalx-pretix-sso:a@example.invalid").hexdigest()
    )


@pytest.mark.parametrize(
    "env, missing",
    [
        ({}, []),
        ({"PRETALX_PRETIX_SSO_API_TOKEN": ""}, None),  # empty env falls back to cfg
        ({"PRETALX_PRETIX_SSO_ISSUER": "https://tickets.example.invalid"}, ["organizer"]),
        (
            {"PRETALX_PRETIX_SSO_ISSUER": "https://tickets.example.invalid",
             "PRETALX_PRETIX_SSO_ORGANIZER": "myorg"},
            [],
        ),
    ],
)
def test_missing_settings(monkeypatch, env, missing):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if missing is not None:
        assert tickets.missing_settings() == missing
    assert tickets.is_configured() == (not tickets.missing_settings())


def test_missing_token_and_issuer_are_named(settings, monkeypatch):
    settings.PLUGIN_SETTINGS = {"pretalx_pretix_sso": {}}
    assert tickets.missing_settings() == ["api_token", "pretix_url", "organizer"]
