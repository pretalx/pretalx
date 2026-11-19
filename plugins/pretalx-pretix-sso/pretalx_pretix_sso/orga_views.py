import inspect
import logging
import time

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from pretalx.common.views.mixins import EventPermissionRequired
from pretalx.person.domain.queries.profile import annotate_speaker_submission_counts
from pretalx.submission.domain.queries.speaker import speakers_for_user
from pretalx.submission.domain.queries.submission import submissions_for_user

from . import tagging, tickets
from .models import TicketOverride

logger = logging.getLogger(__name__)
VIEW_PERMISSION = "person.orga_list_speakerprofile"
# pretalx 2026.3 requires the proposals the user may see (submissions=...);
# 2026.2 doesn't take the argument
COUNTS_NEED_SUBMISSIONS = (
    "submissions" in inspect.signature(annotate_speaker_submission_counts).parameters
)
CHANGE_PERMISSION = "submission.orga_update_submission"


class TicketCheckView(EventPermissionRequired, TemplateView):
    # The page renders immediately with a loading indicator; tickets.js then
    # fetches the table (?partial=1), which is the slow part that calls pretix.
    template_name = "pretalx_pretix_sso/tickets.html"
    partial_template_name = "pretalx_pretix_sso/_tickets_table.html"
    permission_required = VIEW_PERMISSION

    @property
    def is_partial(self):
        return self.request.GET.get("partial") == "1"

    def get_template_names(self):
        return [self.partial_template_name if self.is_partial else self.template_name]

    def dispatch(self, request, *args, **kwargs):
        if "pretalx_pretix_sso" not in request.event.plugin_list:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm(CHANGE_PERMISSION, request.event):
            raise Http404
        action = request.POST.get("action")
        if action == "sync_tag":
            self._sync_tag(request)
        elif action in ("override_on", "override_off"):
            self._set_override(request, action == "override_on")
        else:
            raise Http404
        # Back to the page, but without ?refresh=1: the action already fetched
        # fresh data where needed, and reloads should use the cache again
        query = request.GET.copy()
        query.pop("refresh", None)
        return redirect(
            f"{request.path}?{query.urlencode()}" if query else request.path
        )

    def _set_override(self, request, enabled):
        event = request.event
        profile = (
            speakers_for_user(event, request.user)
            .filter(user__code=request.POST.get("user"))
            .first()
        )
        if not profile:
            raise Http404
        user = profile.user
        if enabled:
            TicketOverride.objects.get_or_create(
                event=event, user=user, defaults={"created_by": request.user}
            )
        else:
            TicketOverride.objects.filter(event=event, user=user).delete()
        logger.info(
            "User %s %s the ticket override for speaker %s on event %s",
            request.user.code,
            "set" if enabled else "removed",
            user.code,
            event.slug,
        )
        event.log_action(
            "pretalx_pretix_sso.override." + ("set" if enabled else "removed"),
            person=request.user,
            orga=True,
            data={"speaker": user.code},
        )

    def _sync_tag(self, request):
        event = request.event
        if not tickets.is_configured():
            logger.info(
                "Tag sync on event %s skipped: ticket check not configured", event.slug
            )
            return
        logger.info(
            "User %s started the %s tag sync on event %s",
            request.user.code,
            tagging.TICKET_TAG,
            event.slug,
        )
        if tickets.runs_in_background():
            self._queue_sync(request)
            return
        # No celery worker: fetch and sync within this request
        started = time.monotonic()
        try:
            holders = tickets.ticket_holders(event, refresh=True)
        except tickets.LOOKUP_ERRORS:
            logger.exception(
                "The %s tag sync for event %s failed: pretix unavailable",
                tagging.TICKET_TAG,
                event.slug,
            )
            tagging.record_sync_failure(event, request.user, tagging.FAILED_PRETIX)
            messages.error(request, _("Could not load orders from pretix."))
            return
        counts = tagging.sync_ticket_tag(event, holders, request.user)
        logger.info(
            "Finished the %s tag sync for event %s in %.1fs",
            tagging.TICKET_TAG,
            event.slug,
            time.monotonic() - started,
        )
        messages.success(
            request,
            " ".join(
                _(
                    'Tag "{tag}" updated: added to {added}, removed from {removed} proposals.'
                ).format(tag=tag, added=added, removed=removed)
                for tag, (added, removed) in counts.items()
            ),
        )

    def _queue_sync(self, request):
        from .tasks import sync_ticket_tag

        event = request.event
        if not tickets.acquire_job(event, "sync"):
            logger.info(
                "User %s asked for a %s tag sync on event %s; one is already running",
                request.user.code,
                tagging.TICKET_TAG,
                event.slug,
            )
            messages.info(request, _("A tag sync is already running."))
            return
        try:
            sync_ticket_tag.apply_async(
                kwargs={"event_id": event.pk, "user_id": request.user.pk}
            )
        except Exception:
            tickets.release_job(event, "sync")
            logger.exception("Could not queue the tag sync for event %s", event.slug)
            messages.error(
                request, _("Could not start the tag sync. Please try again.")
            )
            return
        logger.info(
            "Queued the %s tag sync for event %s", tagging.TICKET_TAG, event.slug
        )
        messages.info(
            request,
            _(
                "The tag sync has started. Its result will appear on this page and in "
                "the activity log in a moment."
            ),
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        event = self.request.event
        ctx["missing_settings"] = tickets.missing_settings()
        ctx["configured"] = not ctx["missing_settings"]
        ctx["pretix_event"] = tickets.pretix_event_slug(event)
        ctx["ticket_tag"] = tagging.TICKET_TAG
        ctx["has_ticket_tag"] = tagging.HAS_TICKET_TAG
        ctx["can_edit"] = self.request.user.has_perm(CHANGE_PERMISSION, event)
        ctx["only_accepted"] = self.request.GET.get("accepted") == "1"
        ctx["rows"] = []
        if not ctx["configured"]:
            return ctx
        if not self.is_partial:
            query = self.request.GET.copy()
            query["partial"] = "1"
            ctx["table_url"] = f"{self.request.path}?{query.urlencode()}"
            return ctx
        ctx["last_sync"] = tagging.last_sync(event)
        if tickets.runs_in_background():
            holders = self._holders_from_background(ctx)
        else:
            holders = self._holders_in_request(ctx)
        if holders is None:
            return ctx

        overridden = tagging.overridden_user_ids(event)
        # Profiles without an account (user is None) are listed too: nothing
        # can match them to a ticket, so they show as missing one
        count_kwargs = {"event": event}
        if COUNTS_NEED_SUBMISSIONS:
            count_kwargs["submissions"] = submissions_for_user(event, self.request.user)
        profiles = annotate_speaker_submission_counts(
            speakers_for_user(event, self.request.user).select_related(
                "user__pretix_customer"
            ),
            **count_kwargs,
        ).order_by("-accepted_submission_count", "name", "user__name")
        for profile in profiles:
            if ctx["only_accepted"] and not profile.accepted_submission_count:
                continue
            ctx["rows"].append(
                {
                    "profile": profile,
                    "status": holders.status(
                        profile.user, profile.user_id in overridden
                    ),
                    "overridden": profile.user_id in overridden,
                    "linked": tickets.customer_identifier(profile.user) is not None,
                }
            )
        # Only speakers who are actually on the programme need a ticket
        ctx["missing_count"] = sum(
            1
            for row in ctx["rows"]
            if not row["status"] and row["profile"].accepted_submission_count
        )
        return ctx

    def _holders_in_request(self, ctx):
        """No celery worker: fetch from pretix within this request if needed."""
        event = self.request.event
        try:
            holders = tickets.ticket_holders(
                event, refresh="refresh" in self.request.GET
            )
        except tickets.LOOKUP_ERRORS:
            logger.exception("pretix ticket lookup failed")
            ctx["load_error"] = True
            return None
        ctx["fetched_at"] = tickets.cached_holders(event)[1]
        return holders

    def _holders_from_background(self, ctx):
        """Never call pretix here: show the cached data, queue a refresh when
        asked for or when there is nothing to show, and let tickets.js poll."""
        event = self.request.event
        holders, fetched_at = tickets.cached_holders(event)
        failed_at = tickets.last_refresh_failed_at(event)
        # After a failure, only retry when asked, not on every poll
        if "refresh" in self.request.GET or (holders is None and not failed_at):
            try:
                tickets.start_refresh(event)
            except Exception:
                logger.exception("Could not queue a pretix refresh for %s", event.slug)
        ctx["refreshing"] = tickets.job_running(event, "refresh")
        ctx["syncing"] = tickets.job_running(event, "sync")
        ctx["pending"] = ctx["refreshing"] or ctx["syncing"]
        ctx["fetched_at"] = fetched_at
        if failed_at and (not fetched_at or failed_at > fetched_at):
            ctx["failed_at"] = failed_at
        if holders is None:
            if ctx["refreshing"]:
                ctx["waiting"] = True
            else:
                ctx["load_error"] = True
        return holders
