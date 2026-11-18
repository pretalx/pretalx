"""Background jobs, run by pretalx's celery worker (autodiscovered from here).

Both jobs hold their per-event lock (see tickets.acquire_job) from the moment
they are queued, and release it when they finish, whatever the outcome.
"""

import logging
import time

from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.event.models import Event
from pretalx.person.models import User

from . import tagging, tickets

logger = logging.getLogger(__name__)


def _event(event_id):
    with scopes_disabled():
        event = Event.objects.filter(pk=event_id).first()
    if not event:
        logger.error("pretix SSO job for unknown event %s", event_id)
    return event


@app.task(name="pretalx_pretix_sso.refresh_tickets")
def refresh_tickets(*, event_id):
    event = _event(event_id)
    if not event:
        return
    try:
        with scope(event=event):
            tickets.refresh_holders(event)
    except tickets.LOOKUP_ERRORS:
        # refresh_holders logged and recorded the failure for the tickets page
        logger.exception("Background pretix ticket refresh failed for %s", event.slug)
    finally:
        tickets.release_job(event, "refresh")


@app.task(name="pretalx_pretix_sso.sync_ticket_tag")
def sync_ticket_tag(*, event_id, user_id):
    event = _event(event_id)
    if not event:
        return
    user = User.objects.filter(pk=user_id).first()
    logger.info(
        "Running the %s tag sync for event %s, requested by user %s",
        tagging.TICKET_TAG,
        event.slug,
        user.code if user else "(deleted)",
    )
    started = time.monotonic()
    try:
        with scope(event=event):
            holders = tickets.refresh_holders(event)
            tagging.sync_ticket_tag(event, holders, user)
    except tickets.LOOKUP_ERRORS:
        logger.exception(
            "The %s tag sync for event %s failed after %.1fs: pretix unavailable",
            tagging.TICKET_TAG,
            event.slug,
            time.monotonic() - started,
        )
        tagging.record_sync_failure(event, user, tagging.FAILED_PRETIX)
    except Exception:
        logger.exception(
            "The %s tag sync for event %s failed after %.1fs",
            tagging.TICKET_TAG,
            event.slug,
            time.monotonic() - started,
        )
        tagging.record_sync_failure(event, user, tagging.FAILED_ERROR)
        raise
    else:
        logger.info(
            "Finished the %s tag sync for event %s in %.1fs",
            tagging.TICKET_TAG,
            event.slug,
            time.monotonic() - started,
        )
    finally:
        tickets.release_job(event, "sync")
