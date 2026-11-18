from unittest import mock

import pytest
import requests
from django.http import Http404
from pretalx_pretix_sso import tickets
from pretalx_pretix_sso.models import PretixCustomer, TicketOverride

from pretalx.common.models import ActivityLog
from pretalx.event.domain.plugins import disable_plugin


def _holders(emails=(), customers=()):
    return tickets.TicketHolders.from_emails(emails, customers)


@pytest.fixture
def pretix():
    """Patch the pretix fetch; set ``pretix.return_value``/``side_effect``."""
    with mock.patch.object(tickets, "_fetch_ticket_holders") as fetch:
        fetch.return_value = _holders()
        yield fetch


def _tagged(event):
    tag = event.tags.filter(tag="needsTicket").first()
    return set(tag.submissions.values_list("title", flat=True)) if tag else set()


def test_page_shell_does_not_call_pretix(tickets_page, pretix):
    response, _ = tickets_page(query="?accepted=1&refresh=1")
    html = response.content.decode()
    pretix.assert_not_called()
    assert "fa-spin" in html and "pretalx_pretix_sso/tickets.js" in html
    assert "?accepted=1&amp;refresh=1&amp;partial=1" in html
    assert "<table" not in html


def test_table_partial_shows_statuses(
    tickets_page, pretix, make_speaker, make_proposal
):
    linked = make_speaker("linked@example.invalid")
    PretixCustomer.objects.create(user=linked, identifier="CUST1")
    by_email = make_speaker("email@example.invalid")
    nobody = make_speaker("nobody@example.invalid")
    # pretalx only lists speakers who have a proposal
    make_proposal("Talk", "accepted", linked, by_email, nobody)
    pretix.return_value = _holders(
        emails={"email@example.invalid"}, customers={"CUST1"}
    )
    response, _ = tickets_page(query="?partial=1")
    html = response.content.decode()
    assert "<html" not in html
    assert "Paid (email)" in html and "fa-link" in html and "Mark as covered" in html


def test_speaker_without_account_needs_a_ticket(tickets_page, pretix, event):
    from pretalx.person.models import SpeakerProfile
    from pretalx.submission.models import Submission

    guest = SpeakerProfile.objects.create(event=event, name="Guest Speaker")
    talk = Submission.objects.create(
        event=event,
        title="Guest talk",
        state="accepted",
        submission_type=event.cfp.default_type,
    )
    talk.speakers.add(guest)
    response, _ = tickets_page(query="?partial=1")
    html = response.content.decode()
    # listed as missing a ticket, without an override (overrides need an account)
    assert "Guest Speaker" in html and "Mark as covered" not in html
    assert "1 speaker with an accepted proposal has no ticket." in " ".join(
        html.split()
    )
    tickets_page("post", data={"action": "sync_tag"})
    assert _tagged(event) == {"Guest talk"}


@pytest.mark.parametrize(
    "error", (requests.ConnectionError("down"), tickets.TicketLookupError("bad"))
)
def test_pretix_failure_shows_inline_error(tickets_page, pretix, error):
    pretix.side_effect = error
    response, _ = tickets_page(query="?partial=1")
    html = response.content.decode()
    assert response.status_code == 200
    assert "alert-danger" in html and "<table" not in html


def test_override_on_and_off(tickets_page, event, admin, make_speaker, make_proposal):
    speaker = make_speaker("comp@example.invalid")
    make_proposal("Talk", "accepted", speaker)
    tickets_page("post", data={"action": "override_on", "user": speaker.code})
    assert TicketOverride.objects.filter(
        event=event, user=speaker, created_by=admin
    ).exists()
    tickets_page("post", data={"action": "override_off", "user": speaker.code})
    assert not TicketOverride.objects.filter(event=event, user=speaker).exists()
    logged = set(ActivityLog.objects.values_list("action_type", flat=True))
    assert {
        "pretalx_pretix_sso.override.set",
        "pretalx_pretix_sso.override.removed",
    } <= logged


def test_override_for_unknown_speaker_is_404(tickets_page):
    with pytest.raises(Http404):
        tickets_page("post", data={"action": "override_on", "user": "NOPE"})


def test_sync_tags_uncovered_proposals_in_every_state_and_type(
    tickets_page, pretix, event, make_speaker, make_proposal
):
    from pretalx.submission.models import Submission, SubmissionType

    paid = make_speaker("paid@example.invalid")
    comp = make_speaker("comp@example.invalid")
    nobody = make_speaker("nobody@example.invalid")
    make_proposal("Paid", "accepted", paid)
    make_proposal("Comp", "confirmed", comp)
    make_proposal("Shared", "accepted", nobody, paid)
    for state in (
        "submitted",
        "accepted",
        "confirmed",
        "rejected",
        "withdrawn",
        "canceled",
    ):
        make_proposal(f"Uncovered {state}", state, nobody)
    workshop = make_proposal("Uncovered workshop", "accepted", nobody)
    workshop.submission_type = SubmissionType.objects.create(
        event=event, name="Workshop"
    )
    workshop.save()
    draft = make_proposal("Draft", "draft", nobody)
    TicketOverride.objects.create(event=event, user=comp)
    pretix.return_value = _holders(emails={"paid@example.invalid"})

    _, messages = tickets_page("post", data={"action": "sync_tag"})
    expected = {
        "Uncovered submitted",
        "Uncovered accepted",
        "Uncovered confirmed",
        "Uncovered rejected",
        "Uncovered withdrawn",
        "Uncovered canceled",
        "Uncovered workshop",
    }
    assert _tagged(event) == expected
    assert f"added to {len(expected)}" in messages[-1]
    assert not Submission.all_objects.get(pk=draft.pk).tags.exists()  # drafts untouched
    assert ActivityLog.objects.filter(
        action_type="pretalx_pretix_sso.tag.synced"
    ).exists()

    # the tag comes off again once the speaker is covered
    pretix.return_value = _holders(
        emails={"paid@example.invalid", "nobody@example.invalid"}
    )
    tickets_page("post", data={"action": "sync_tag"})
    assert _tagged(event) == set()


def test_sync_always_fetches_fresh_data(tickets_page, pretix, event):
    tickets.ticket_holders(event)  # warm the cache
    tickets_page("post", data={"action": "sync_tag"})
    assert pretix.call_count == 2


def test_actions_redirect_without_refresh(
    tickets_page, make_speaker, make_proposal, event
):
    speaker = make_speaker("sp@example.invalid")
    make_proposal("Talk", "accepted", speaker)
    base = f"/orga/event/{event.slug}/p/pretix-tickets/"
    response, _ = tickets_page(
        "post", "?accepted=1&refresh=1", {"action": "override_on", "user": speaker.code}
    )
    assert response.url == base + "?accepted=1"
    response, _ = tickets_page(
        "post", "?refresh=1", {"action": "override_off", "user": speaker.code}
    )
    assert response.url == base


def test_actions_need_change_permission(tickets_page, event, make_speaker):
    from pretalx.event.models import Team

    reviewer = make_speaker("reviewer@example.invalid")
    team = Team.objects.create(
        organiser=event.organiser,
        name="Reviewers",
        is_reviewer=True,
        can_change_submissions=False,
        all_events=True,
    )
    team.members.add(reviewer)
    with pytest.raises(Http404):
        tickets_page("post", data={"action": "sync_tag"}, user=reviewer)


def test_page_404_when_plugin_disabled(tickets_page, event):
    disable_plugin(event, "pretalx_pretix_sso")
    with pytest.raises(Http404):
        tickets_page()


def test_missing_count_only_includes_accepted_speakers(
    tickets_page, pretix, make_speaker, make_proposal
):
    make_proposal("Accepted", "accepted", make_speaker("accepted@example.invalid"))
    make_proposal("Rejected", "rejected", make_speaker("rejected@example.invalid"))
    make_proposal("Submitted", "submitted", make_speaker("submitted@example.invalid"))
    response, _ = tickets_page(query="?partial=1")
    html = " ".join(response.content.decode().split())
    assert "1 speaker with an accepted proposal has no ticket." in html


def test_activity_log_entries_are_readable(
    tickets_page, pretix, event, make_speaker, make_proposal
):
    speaker = make_speaker("comp@example.invalid")
    make_proposal("Talk", "accepted", speaker)
    tickets_page("post", data={"action": "override_on", "user": speaker.code})
    tickets_page("post", data={"action": "override_off", "user": speaker.code})
    tickets_page("post", data={"action": "sync_tag"})
    shown = [str(log.display) for log in ActivityLog.objects.order_by("pk")]
    assert not any(text.startswith("pretalx_pretix_sso.") for text in shown), shown
    assert any("marked as covered" in text for text in shown)
    assert any("override was removed" in text for text in shown)
    assert any(
        '"needsTicket" tag was synced' in text and "added to 1" in text
        for text in shown
    )


def test_unconfigured_page_names_missing_settings(tickets_page, monkeypatch):
    monkeypatch.setenv("PRETALX_PRETIX_SSO_ISSUER", "https://tickets.example.invalid")
    response, _ = tickets_page()
    html = response.content.decode()
    assert "<code>organizer</code>" in html and "own domain" in html
    assert "<code>api_token</code>" not in html  # the token is configured


def test_nav_links_to_tickets_page_for_organisers(event, admin, make_speaker):
    from django.test import Client

    from pretalx.event.models import Team

    tickets_url = f"/orga/event/{event.slug}/p/pretix-tickets/"
    client = Client(HTTP_HOST="pretalx.example.invalid")
    client.force_login(admin)
    html = client.get(f"/orga/event/{event.slug}/", secure=True).content.decode()
    assert tickets_url in html
    # a team member who cannot see speakers gets no link
    member = make_speaker("member@example.invalid")
    team = Team.objects.create(
        organiser=event.organiser,
        name="Settings only",
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=False,
    )
    team.members.add(member)
    client.force_login(member)
    html = client.get(f"/orga/event/{event.slug}/", secure=True).content.decode()
    assert tickets_url not in html


def _has_ticket(event):
    tag = event.tags.filter(tag="hasTicket").first()
    return set(tag.submissions.values_list("title", flat=True)) if tag else set()


def test_sync_tags_proposals_with_paid_tickets(
    tickets_page, pretix, event, make_speaker, make_proposal
):
    from pretalx.submission.models import Submission

    by_email = make_speaker("paid@example.invalid")
    by_account = make_speaker("linked@example.invalid")
    PretixCustomer.objects.create(user=by_account, identifier="CUST1")
    comp = make_speaker("comp@example.invalid")
    nobody = make_speaker("nobody@example.invalid")
    make_proposal("Paid by email", "accepted", by_email)
    make_proposal("Paid by account", "rejected", by_account)
    make_proposal("Shared", "submitted", nobody, by_email)
    make_proposal("Comp", "confirmed", comp)
    make_proposal("Nobody", "accepted", nobody)
    draft = make_proposal("Draft", "draft", by_email)
    TicketOverride.objects.create(event=event, user=comp)
    pretix.return_value = _holders(emails={"paid@example.invalid"}, customers={"CUST1"})

    _, messages = tickets_page("post", data={"action": "sync_tag"})

    assert _has_ticket(event) == {"Paid by email", "Paid by account", "Shared"}
    # An override covers the speaker but is not a ticket: neither tag
    assert _tagged(event) == {"Nobody"}
    assert 'Tag "hasTicket" updated: added to 3, removed from 0' in messages[-1]
    assert not Submission.all_objects.get(pk=draft.pk).tags.exists()
    log = ActivityLog.objects.get(action_type="pretalx_pretix_sso.tag.synced")
    assert log.json_data["has_ticket"] == {"tag": "hasTicket", "added": 3, "removed": 0}
    assert '"hasTicket" tag: added to 3, removed from 0' in log.display

    # The tag comes off once the ticket is gone
    pretix.return_value = _holders(customers={"CUST1"})
    _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert _has_ticket(event) == {"Paid by account"}
    assert 'Tag "hasTicket" updated: added to 0, removed from 2' in messages[-1]


def test_old_sync_log_entries_still_display(event, admin):
    event.log_action(
        "pretalx_pretix_sso.tag.synced",
        person=admin,
        orga=True,
        data={"tag": "needsTicket", "added": 2, "removed": 1},
    )
    display = ActivityLog.objects.get(
        action_type="pretalx_pretix_sso.tag.synced"
    ).display
    assert '"needsTicket" tag was synced' in display and "hasTicket" not in display
