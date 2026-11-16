"""With a celery worker, pretix is only ever called from background jobs."""

from unittest import mock

import pytest
import requests

from pretalx.common.models import ActivityLog
from pretalx_pretix_sso import tagging, tasks, tickets


class FakeWorker:
    """Collects queued jobs instead of sending them to celery; run() executes
    them the way the worker would, so tests control when jobs complete."""

    def __init__(self):
        self.queue = []

    def queue_for(self, task):
        def apply_async(kwargs):
            self.queue.append((task, kwargs))

        return apply_async

    def run(self):
        jobs, self.queue = self.queue, []
        for task, kwargs in jobs:
            task(**kwargs)
        return len(jobs)


@pytest.fixture
def worker(settings):
    settings.HAS_CELERY = True
    fake = FakeWorker()
    with mock.patch.object(
        tasks.refresh_tickets, "apply_async", side_effect=fake.queue_for(tasks.refresh_tickets)
    ), mock.patch.object(
        tasks.sync_ticket_tag, "apply_async", side_effect=fake.queue_for(tasks.sync_ticket_tag)
    ):
        yield fake


@pytest.fixture
def pretix():
    with mock.patch.object(tickets, "_fetch_ticket_holders") as fetch:
        fetch.return_value = tickets.TicketHolders.from_emails({"paid@example.invalid"})
        yield fetch


@pytest.fixture
def speakers(make_speaker, make_proposal):
    paid = make_speaker("paid@example.invalid")
    nobody = make_speaker("nobody@example.invalid")
    make_proposal("Paid talk", "accepted", paid)
    make_proposal("Uncovered talk", "accepted", nobody)
    return paid, nobody


def _html(response):
    return " ".join(response.content.decode().split())


def test_first_load_queues_refresh_without_calling_pretix(tickets_page, worker, pretix):
    response, _ = tickets_page(query="?partial=1")
    html = _html(response)
    pretix.assert_not_called()
    assert len(worker.queue) == 1
    assert 'data-pending="1"' in html and "Loading tickets from pretix" in html


def test_polling_does_not_queue_again_while_job_is_pending(tickets_page, worker, pretix):
    for _ in range(3):
        tickets_page(query="?partial=1")
    assert len(worker.queue) == 1


def test_table_appears_once_the_job_has_run(tickets_page, worker, pretix, speakers):
    tickets_page(query="?partial=1")
    assert worker.run() == 1
    response, _ = tickets_page(query="?partial=1")
    html = _html(response)
    assert 'data-pending=""' in html
    assert "updated" in html and "Paid talk" not in html  # speakers table, not proposals
    assert "<table" in html and "None" in html
    pretix.assert_called_once()


def test_refresh_shows_cached_data_while_refreshing(tickets_page, worker, pretix, speakers, event):
    tickets.refresh_holders(event)  # warm cache
    response, _ = tickets_page(query="?partial=1&refresh=1")
    html = _html(response)
    assert "<table" in html and "Refreshing" in html and 'data-pending="1"' in html
    assert len(worker.queue) == 1
    worker.run()
    response, _ = tickets_page(query="?partial=1")
    assert "Refreshing" not in _html(response)


def test_failed_refresh_is_reported_and_not_retried_by_polls(tickets_page, worker, pretix):
    pretix.side_effect = requests.ConnectionError("down")
    tickets_page(query="?partial=1")
    worker.run()  # the job fails
    response, _ = tickets_page(query="?partial=1")
    html = _html(response)
    assert "Could not load orders from pretix" in html and 'data-pending=""' in html
    assert worker.queue == []  # polls do not hammer a failing pretix
    tickets_page(query="?partial=1&refresh=1")  # "Try again"
    assert len(worker.queue) == 1


def test_failed_refresh_with_older_data_shows_warning(tickets_page, worker, pretix, speakers, event):
    tickets.refresh_holders(event)
    pretix.side_effect = requests.ConnectionError("down")
    tickets_page(query="?partial=1&refresh=1")
    worker.run()
    response, _ = tickets_page(query="?partial=1")
    html = _html(response)
    assert "<table" in html and "last refresh from pretix failed" in html


def test_sync_runs_in_background(tickets_page, worker, pretix, speakers, event, admin):
    _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert "has started" in messages[-1]
    pretix.assert_not_called()
    _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert "already running" in messages[-1]
    response, _ = tickets_page(query="?partial=1")
    assert "Tag sync running" in _html(response)

    assert worker.run() == 2  # the sync, plus the table's initial refresh
    tag = tagging.ticket_tag(event)
    assert set(tag.submissions.values_list("title", flat=True)) == {"Uncovered talk"}
    log = ActivityLog.objects.get(action_type=tagging.SYNC_ACTION)
    assert log.person == admin
    response, _ = tickets_page(query="?partial=1")
    html = _html(response)
    assert "Last tag sync" in html and "added to 1" in html and "Tag sync running" not in html


def test_sync_can_run_again_after_finishing(tickets_page, worker, pretix, speakers):
    tickets_page("post", data={"action": "sync_tag"})
    worker.run()
    _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert "has started" in messages[-1]


def test_queue_failure_releases_lock(tickets_page, worker, pretix, event, settings):
    with mock.patch.object(
        tasks.sync_ticket_tag, "apply_async", side_effect=ConnectionError("broker down")
    ):
        _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert "Could not start" in messages[-1]
    assert not tickets.job_running(event, "sync")
    with mock.patch.object(
        tasks.refresh_tickets, "apply_async", side_effect=ConnectionError("broker down")
    ):
        response, _ = tickets_page(query="?partial=1")
    assert response.status_code == 200 and "Could not load orders" in _html(response)
    assert not tickets.job_running(event, "refresh")


def test_job_releases_lock_even_on_unexpected_error(event, pretix):
    pretix.side_effect = RuntimeError("bug")
    assert tickets.acquire_job(event, "refresh")
    with pytest.raises(RuntimeError):
        tasks.refresh_tickets(event_id=event.pk)
    assert not tickets.job_running(event, "refresh")


def test_jobs_for_unknown_events_do_nothing(pretix):
    tasks.refresh_tickets(event_id=999999)
    tasks.sync_ticket_tag(event_id=999999, user_id=1)
    pretix.assert_not_called()


def test_tasks_are_registered_with_pretalx_celery():
    from pretalx.celery_app import app

    assert "pretalx_pretix_sso.refresh_tickets" in app.tasks
    assert "pretalx_pretix_sso.sync_ticket_tag" in app.tasks


def test_without_worker_everything_stays_in_the_request(tickets_page, pretix, speakers, settings):
    settings.HAS_CELERY = False
    response, _ = tickets_page(query="?partial=1")
    assert "<table" in _html(response)
    pretix.assert_called_once()
    _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert "added to 1" in messages[-1]


def test_results_are_shown_in_one_info_box(tickets_page, worker, pretix, speakers, event):
    import re

    tickets.refresh_holders(event)
    tickets_page("post", data={"action": "sync_tag"})
    worker.run()
    html = _html(tickets_page(query="?partial=1")[0])
    box = re.search(r'<div class="alert alert-info pretix-tickets-status">(.*?)</div> </div>', html)
    assert box, html
    content = box.group(1)
    assert "1 speaker with an accepted proposal has no ticket." in content
    assert "Ticket data from pretix, updated" in content
    assert "Last tag sync" in content and "added to 1" in content
    assert "updated" not in html.replace(content, "")  # nothing left outside the box


def test_no_empty_info_box(tickets_page, settings, event):
    settings.HAS_CELERY = False
    with mock.patch.object(
        tickets, "_fetch_ticket_holders", return_value=tickets.TicketHolders.from_emails()
    ), mock.patch.object(tickets, "cached_holders", return_value=(None, None)):
        html = _html(tickets_page(query="?partial=1")[0])
    assert "pretix-tickets-status" not in html  # no speakers, no data age, no sync yet


def _sync_logs(caplog):
    return [
        r.getMessage() for r in caplog.records if r.name.startswith("pretalx_pretix_sso")
    ]


def test_background_sync_logs_its_lifecycle(tickets_page, worker, pretix, speakers, admin, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="pretalx_pretix_sso")
    tickets_page("post", data={"action": "sync_tag"})
    tickets_page("post", data={"action": "sync_tag"})  # refused: already running
    worker.run()
    logs = _sync_logs(caplog)
    order = [
        f"User {admin.code} started the needsTicket tag sync",
        "Queued the needsTicket tag sync",
        "one is already running",
        f"Running the needsTicket tag sync for event test, requested by user {admin.code}",
        "needsTicket tag sync on event test: added to 1",
        "Finished the needsTicket tag sync for event test in",
    ]
    positions = [next(i for i, m in enumerate(logs) if text in m) for text in order]
    assert positions == sorted(positions), logs


@pytest.mark.parametrize(
    "error, reason, shown",
    [
        (requests.ConnectionError("down"), "pretix", "pretix could not be reached"),
        (RuntimeError("bug"), "error", "unexpected error"),
    ],
)
def test_failed_background_sync_is_logged_and_shown(
    tickets_page, worker, pretix, speakers, event, admin, caplog, error, reason, shown
):
    import logging

    caplog.set_level(logging.INFO, logger="pretalx_pretix_sso")
    tickets.refresh_holders(event)  # so the table itself has data
    tickets_page("post", data={"action": "sync_tag"})
    pretix.side_effect = error
    if isinstance(error, RuntimeError):
        with pytest.raises(RuntimeError):  # unexpected errors still fail the job
            worker.run()
    else:
        worker.run()
    log = ActivityLog.objects.get(action_type=tagging.SYNC_FAILED_ACTION)
    assert log.person == admin and log.json_data == {"tag": "needsTicket", "reason": reason}
    assert shown in str(log.display)
    assert any("tag sync for event test failed after" in m for m in _sync_logs(caplog))
    assert not tickets.job_running(event, "sync")
    pretix.side_effect = None
    html = _html(tickets_page(query="?partial=1")[0])
    assert "text-danger" in html and shown in html and "Last tag sync" in html
    assert not tagging.ticket_tag(event).submissions.exists()  # nothing was changed


def test_failed_sync_without_worker_is_recorded(tickets_page, pretix, speakers, settings):
    settings.HAS_CELERY = False
    pretix.side_effect = requests.ConnectionError("down")
    _, messages = tickets_page("post", data={"action": "sync_tag"})
    assert "Could not load orders" in messages[-1]
    assert ActivityLog.objects.filter(action_type=tagging.SYNC_FAILED_ACTION).exists()


def test_successful_sync_after_failure_replaces_it_in_the_box(
    tickets_page, worker, pretix, speakers, event
):
    tickets.refresh_holders(event)
    pretix.side_effect = requests.ConnectionError("down")
    tickets_page("post", data={"action": "sync_tag"})
    worker.run()
    pretix.side_effect = None
    tickets_page("post", data={"action": "sync_tag"})
    worker.run()
    html = _html(tickets_page(query="?partial=1")[0])
    assert "added to 1" in html and "text-danger" not in html
