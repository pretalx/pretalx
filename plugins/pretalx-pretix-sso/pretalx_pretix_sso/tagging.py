"""Keep the needsTicket tag on the proposals whose speakers have no ticket, and
the hasTicket tag on those where a speaker holds a paid ticket."""

import logging

from django.db import transaction

from pretalx.common.models import ActivityLog
from pretalx.submission.models import Tag

from .models import TicketOverride
from .tickets import PAID_ACCOUNT, PAID_EMAIL

logger = logging.getLogger(__name__)
TICKET_TAG = "needsTicket"
# Only paid pretix tickets count; an organiser override is not a ticket, so a
# proposal covered only by an override has neither tag
HAS_TICKET_TAG = "hasTicket"
PAID = (PAID_ACCOUNT, PAID_EMAIL)
TAG_COLORS = {TICKET_TAG: "#b23e65", HAS_TICKET_TAG: "#2e7d4f"}
SYNC_ACTION = "pretalx_pretix_sso.tag.synced"
SYNC_FAILED_ACTION = "pretalx_pretix_sso.tag.sync_failed"
# Why a sync failed, as stored in the activity log
FAILED_PRETIX = "pretix"  # pretix unreachable or returned unexpected data
FAILED_ERROR = "error"  # anything else; details are in the server log


def ticket_tag(event, name=TICKET_TAG):
    """One of the event's ticket tags, created if missing (tag names are unique
    per event)."""
    tag, _created = Tag.objects.get_or_create(
        event=event, tag=name, defaults={"color": TAG_COLORS[name]}
    )
    return tag


def overridden_user_ids(event):
    return set(
        TicketOverride.objects.filter(event=event).values_list("user_id", flat=True)
    )


def sync_ticket_tag(event, holders, user):
    """Tag every proposal without a covered speaker with needsTicket and every
    proposal with a paying speaker with hasTicket, untag the rest, and record
    the result in the activity log. Returns {tag name: (added, removed)}."""
    overridden = overridden_user_ids(event)
    counts = {TICKET_TAG: [0, 0], HAS_TICKET_TAG: [0, 0]}
    with transaction.atomic():
        tags = {name: ticket_tag(event, name) for name in counts}
        tagged = {
            name: set(tag.submissions.values_list("pk", flat=True))
            for name, tag in tags.items()
        }
        # Speakers are SpeakerProfiles; tickets and overrides belong to their user
        submissions = event.submissions.prefetch_related(
            "speakers__user__pretix_customer"
        )
        # Every proposal in any state and of any submission type (pretalx
        # already leaves out drafts and deleted ones) needs a ticket until
        # any of its speakers is covered
        for submission in submissions:
            statuses = [
                holders.status(speaker.user, speaker.user_id in overridden)
                for speaker in submission.speakers.all()
            ]
            wanted = {
                TICKET_TAG: not any(statuses),
                HAS_TICKET_TAG: any(status in PAID for status in statuses),
            }
            for name, want in wanted.items():
                if want and submission.pk not in tagged[name]:
                    submission.tags.add(tags[name])
                    counts[name][0] += 1
                elif not want and submission.pk in tagged[name]:
                    submission.tags.remove(tags[name])
                    counts[name][1] += 1
    for name, (added, removed) in counts.items():
        logger.info(
            "%s tag sync on event %s: added to %d, removed from %d proposals",
            name,
            event.slug,
            added,
            removed,
        )
    (added, removed), (has_added, has_removed) = (
        counts[TICKET_TAG],
        counts[HAS_TICKET_TAG],
    )
    event.log_action(
        SYNC_ACTION,
        person=user,
        orga=True,
        data={
            "tag": TICKET_TAG,
            "added": added,
            "removed": removed,
            "has_ticket": {
                "tag": HAS_TICKET_TAG,
                "added": has_added,
                "removed": has_removed,
            },
        },
    )
    return {name: tuple(pair) for name, pair in counts.items()}


def record_sync_failure(event, user, reason):
    """Put a failed sync in the activity log, so organisers see it failed
    rather than just never finishing."""
    event.log_action(
        SYNC_FAILED_ACTION,
        person=user,
        orga=True,
        data={"tag": TICKET_TAG, "reason": reason},
    )


def last_sync(event):
    """The most recent tag sync's activity log entry, successful or failed."""
    return (
        ActivityLog.objects.filter(
            event=event, action_type__in=(SYNC_ACTION, SYNC_FAILED_ACTION)
        )
        # The page shows entry.display, which reads the event (newer pretalx
        # refuses to load related objects lazily)
        .select_related("event", "person")
        .order_by("-timestamp", "-pk")
        .first()
    )
