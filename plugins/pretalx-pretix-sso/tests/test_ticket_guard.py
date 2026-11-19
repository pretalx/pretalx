import datetime as dt
from unittest import mock

import pytest
from django.test import Client
from pretalx_pretix_sso import ticket_guard, tickets
from pretalx_pretix_sso.models import TicketOverride


def _holders(*emails):
    return tickets.TicketHolders.from_emails(emails=emails)


@pytest.fixture
def fetch():
    """pretix, mocked: set .return_value / .side_effect; count .call_count."""
    with mock.patch.object(tickets, "_fetch_ticket_holders") as fetch:
        fetch.return_value = _holders()
        yield fetch


def _accept(submission, state="accepted"):
    from pretalx.submission.domain.submission import set_submission_state

    set_submission_state(submission, state, orga=True)
    submission.refresh_from_db()
    return submission.state


def test_accept_refused_without_ticket(event, make_speaker, make_proposal, fetch):
    from pretalx.common.exceptions import SubmissionError

    proposal = make_proposal(
        "No ticket", "submitted", make_speaker("a@example.invalid")
    )
    with pytest.raises(SubmissionError, match="none of its speakers has a paid ticket"):
        _accept(proposal)
    # Loaded with its event, as pretalx's views do
    proposal = type(proposal).objects.select_related("event").get(pk=proposal.pk)
    assert proposal.state == "submitted"
    # Straight to confirmed is refused too
    with pytest.raises(SubmissionError):
        _accept(proposal, "confirmed")


def test_accept_allowed_with_ticket(event, make_speaker, make_proposal, fetch):
    fetch.return_value = _holders("b@example.invalid")
    speakers = (make_speaker("a@example.invalid"), make_speaker("b@example.invalid"))
    proposal = make_proposal("One ticket", "submitted", *speakers)
    assert _accept(proposal) == "accepted"


def test_accept_allowed_with_override(event, admin, make_speaker, make_proposal, fetch):
    speaker = make_speaker("a@example.invalid")
    TicketOverride.objects.create(event=event, user=speaker, created_by=admin)
    proposal = make_proposal("Covered", "submitted", speaker)
    assert _accept(proposal) == "accepted"
    assert fetch.call_count == 0  # an override needs no pretix request


def test_fresh_ticket_found_by_refetching_stale_cache(
    event, make_speaker, make_proposal, fetch
):
    proposal = make_proposal(
        "Late buyer", "submitted", make_speaker("a@example.invalid")
    )
    tickets.refresh_holders(event)  # cached: no tickets
    fetch.return_value = _holders("a@example.invalid")  # bought one since
    with mock.patch.object(
        ticket_guard,
        "now",
        return_value=dt.datetime.now(tz=dt.UTC) + dt.timedelta(minutes=5),
    ):
        assert _accept(proposal) == "accepted"
    assert fetch.call_count == 2


def test_bulk_refusals_fetch_pretix_once_per_minute(
    event, make_speaker, make_proposal, fetch
):
    from pretalx.common.exceptions import SubmissionError

    proposals = [
        make_proposal(f"P{i}", "submitted", make_speaker(f"s{i}@example.invalid"))
        for i in range(3)
    ]
    for proposal in proposals:
        with pytest.raises(SubmissionError):
            _accept(proposal)
    assert fetch.call_count == 1


def test_pretix_down_refuses_with_message(event, make_speaker, make_proposal, fetch):
    from pretalx.common.exceptions import SubmissionError

    fetch.side_effect = tickets.TicketLookupError("down")
    proposal = make_proposal("Down", "submitted", make_speaker("a@example.invalid"))
    with pytest.raises(SubmissionError, match="could not be checked"):
        _accept(proposal)


def test_other_transitions_not_blocked(event, make_speaker, make_proposal, fetch):
    speaker = make_speaker("a@example.invalid")
    accepted = make_proposal("Already accepted", "accepted", speaker)
    assert _accept(accepted, "confirmed") == "confirmed"
    submitted = make_proposal("To reject", "submitted", speaker)
    assert _accept(submitted, "rejected") == "rejected"
    assert fetch.call_count == 0


def test_not_blocked_when_ticket_check_unconfigured(
    event, make_speaker, make_proposal, fetch
):
    proposal = make_proposal(
        "Unconfigured", "submitted", make_speaker("a@example.invalid")
    )
    with mock.patch.object(tickets, "is_configured", return_value=False):
        assert _accept(proposal) == "accepted"


def _orga_client(admin):
    client = Client(HTTP_HOST="pretalx.example.invalid")
    client.force_login(admin)
    return client


def test_banner_on_proposal_pages(event, admin, make_speaker, make_proposal, fetch):
    speaker = make_speaker("a@example.invalid")
    proposal = make_proposal("Bannered", "submitted", speaker)
    url = f"/orga/event/{event.slug}/submissions/{proposal.code}/"
    client = _orga_client(admin)
    # Nothing cached (as usual in production): the banner fetches once
    html = client.get(url).content.decode()
    assert "No speaker of this proposal has a paid pretix ticket" in html
    assert fetch.call_count == 1
    # Further page views use the cache
    client.get(url)
    assert fetch.call_count == 1
    TicketOverride.objects.create(event=event, user=speaker, created_by=admin)
    assert "has a paid pretix ticket" not in client.get(url).content.decode()


def test_banner_when_pretix_is_down(event, admin, make_speaker, make_proposal, fetch):
    fetch.side_effect = tickets.TicketLookupError("down")
    proposal = make_proposal("Down", "submitted", make_speaker("a@example.invalid"))
    url = f"/orga/event/{event.slug}/submissions/{proposal.code}/"
    response = _orga_client(admin).get(url)
    assert response.status_code == 200
    assert "could not be checked" in response.content.decode()


def test_dashboard_tile_counts_accepted_without_ticket(
    event, admin, make_speaker, make_proposal, fetch
):
    fetch.return_value = _holders("paid@example.invalid")
    make_proposal("Accepted, no ticket", "accepted", make_speaker("a@example.invalid"))
    make_proposal(
        "Confirmed, no ticket", "confirmed", make_speaker("b@example.invalid")
    )
    make_proposal("Accepted, paid", "accepted", make_speaker("paid@example.invalid"))
    make_proposal(
        "Submitted, no ticket", "submitted", make_speaker("c@example.invalid")
    )
    from pretalx_pretix_sso.signals import ticket_tile

    # Nothing cached: the tile fetches
    (tile,) = ticket_tile(event)
    assert tile["large"] == 2
    assert tile["url"].endswith("/p/pretix-tickets/")
    assert fetch.call_count == 1
    html = _orga_client(admin).get(f"/orga/event/{event.slug}/").content.decode()
    assert "accepted sessions without a pretix ticket" in html
    assert fetch.call_count == 1


def test_dashboard_tile_when_pretix_is_down(event, make_speaker, make_proposal, fetch):
    fetch.side_effect = tickets.TicketLookupError("down")
    make_proposal("Accepted", "accepted", make_speaker("a@example.invalid"))
    from pretalx_pretix_sso.signals import ticket_tile

    (tile,) = ticket_tile(event)
    assert tile["small"] == "pretix tickets could not be checked"


def test_review_dashboard_saves_the_rest_and_reports_refusals(
    event, admin, make_speaker, make_proposal, fetch
):
    from django.contrib.messages import get_messages

    fetch.return_value = _holders("paid@example.invalid")
    paid = make_proposal("Paid", "submitted", make_speaker("paid@example.invalid"))
    unpaid = make_proposal("Unpaid", "submitted", make_speaker("a@example.invalid"))
    rejected = make_proposal("Rejected", "submitted", make_speaker("b@example.invalid"))
    client = _orga_client(admin)
    response = client.post(
        f"/orga/event/{event.slug}/reviews/",
        {
            f"s-{paid.code}": "accept",
            f"s-{unpaid.code}": "accept",
            f"s-{rejected.code}": "reject",
        },
    )
    # pretalx renders the dashboard again after saving
    assert response.status_code == 200
    states = {
        p.title: (p.refresh_from_db() or p.state) for p in (paid, unpaid, rejected)
    }
    assert states == {"Paid": "accepted", "Unpaid": "submitted", "Rejected": "rejected"}
    texts = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("“Unpaid” was not accepted" in t for t in texts)


def test_review_dashboard_all_refused_shows_only_reasons(
    event, admin, make_speaker, make_proposal, fetch
):
    from django.contrib.messages import get_messages

    unpaid = make_proposal("Unpaid", "submitted", make_speaker("a@example.invalid"))
    response = _orga_client(admin).post(
        f"/orga/event/{event.slug}/reviews/", {f"s-{unpaid.code}": "accept"}
    )
    assert response.status_code == 302
    texts = [str(m) for m in get_messages(response.wsgi_request)]
    assert len(texts) == 1
    assert "“Unpaid” was not accepted" in texts[0]
