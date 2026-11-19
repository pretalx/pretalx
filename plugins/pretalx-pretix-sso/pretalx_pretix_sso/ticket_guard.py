"""Whether a proposal is covered for pretix tickets, for blocking acceptance and
for the organiser banner and dashboard tile.

A proposal is covered when any of its speakers holds a paid ticket in the pretix
event or an organiser marked them as covered (TicketOverride): the same rule as
the needsTicket tag (tagging.sync_ticket_tag).
"""

import datetime as dt
import logging

from django.utils.timezone import now
from django.utils.translation import gettext

from . import tickets
from .tagging import overridden_user_ids

logger = logging.getLogger(__name__)

# Before refusing an acceptance, fetch from pretix again if the cached ticket
# holders are older than this, in case the speaker has just bought a ticket.
# At most one pretix request per minute, also for bulk acceptance.
REFRESH_AFTER = dt.timedelta(minutes=1)


def _speaker_users(submission):
    return [
        speaker.user
        for speaker in submission.speakers.select_related("user__pretix_customer")
    ]


def _covered(users, holders, overridden):
    return any(holders.status(user, user.pk in overridden) for user in users if user)


def is_covered(event, submission, *, refresh=False, fetch_missing=False):
    """True or False, or None when no ticket data is cached and neither
    ``refresh`` nor ``fetch_missing`` is set.

    ``fetch_missing``: fetch from pretix when nothing is cached (the banner;
    the cache lasts an hour and is per web task in production, so it is often
    empty). ``refresh``: also fetch when the cached data says "not covered" and
    is older than REFRESH_AFTER (acceptance). pretix errors
    (tickets.LOOKUP_ERRORS) are raised."""
    users = _speaker_users(submission)
    overridden = overridden_user_ids(event)
    if any(user and user.pk in overridden for user in users):
        return True
    holders, fetched_at = tickets.cached_holders(event)
    if holders is not None and _covered(users, holders, overridden):
        return True
    if holders is None and (refresh or fetch_missing):
        return _covered(users, tickets.refresh_holders(event), overridden)
    if holders is None:
        return None
    if refresh and now() - fetched_at > REFRESH_AFTER:
        return _covered(users, tickets.refresh_holders(event), overridden)
    return False


def uncovered(event, submissions):
    """The proposals among ``submissions`` that are not covered. Uses the
    cached ticket data, fetching from pretix only when nothing is cached
    (pretix errors, tickets.LOOKUP_ERRORS, are raised). Pass the proposals with
    prefetch_related("speakers__user__pretix_customer")."""
    if not submissions:
        return []
    holders = tickets.ticket_holders(event)
    overridden = overridden_user_ids(event)
    return [
        submission
        for submission in submissions
        if not _covered(
            [speaker.user for speaker in submission.speakers.all()], holders, overridden
        )
    ]


def refusal(event, submission):
    """Why ``submission`` may not be accepted, as a message for organisers, or
    None if a speaker is covered. May fetch from pretix (see is_covered)."""
    try:
        covered = is_covered(event, submission, refresh=True)
    except tickets.LOOKUP_ERRORS:
        logger.warning(
            "Refused to accept proposal %s on event %s: pretix unreachable",
            submission.code,
            event.slug,
        )
        return gettext(
            "“{title}” was not accepted: the pretix tickets could not be "
            "checked. Try again later, or mark a speaker as covered on the "
            "pretix tickets page."
        ).format(title=submission.title)
    if covered:
        return None
    logger.info(
        "Refused to accept proposal %s on event %s: no speaker has a ticket",
        submission.code,
        event.slug,
    )
    return gettext(
        "“{title}” was not accepted: none of its speakers has a paid ticket in "
        "pretix. If a speaker is covered another way, mark them as covered on "
        "the pretix tickets page."
    ).format(title=submission.title)
