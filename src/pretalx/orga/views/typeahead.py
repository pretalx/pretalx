# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
from contextlib import suppress

from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy as _n
from django_scopes import scopes_disabled

from pretalx.event.domain.queries.team import speaker_access_events_for_user
from pretalx.event.models import Organiser
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import Submission


def is_exact_match(query, *values):
    query = query.strip().lower()
    return bool(query) and any(
        value and str(value).strip().lower() == query for value in values
    )


def serialize_user(user):
    return {"type": "user", "name": str(user), "url": "/orga/me"}


def serialize_orga(orga, query=""):
    return {
        "type": "organiser",
        "name": str(orga.name),
        "url": orga.orga_urls.base,
        "exact": is_exact_match(query, orga.slug, orga.name),
    }


def serialize_event(event, query=""):
    return {
        "type": "event",
        "name": str(event.name),
        "url": event.orga_urls.base,
        "organiser": str(event.organiser.name),
        "date_range": event.get_date_range_display(),
        "color": event.visible_primary_color,
        "exact": is_exact_match(query, event.slug, event.name),
    }


def serialize_submission(submission, query=""):
    return {
        "type": "submission",
        "name": _n("Session", "Sessions", 1) + f" {submission.title}",
        "url": submission.orga_urls.base,
        "event": str(submission.event.name),
        "exact": is_exact_match(query, submission.code, submission.title),
    }


def serialize_speaker(speaker, query=""):
    name = speaker.get_display_name()
    return {
        "type": "speaker",
        "name": _n("Speaker", "Speakers", 1) + f" {name}",
        "url": speaker.orga_urls.base,
        "event": str(speaker.event.name),
        "exact": is_exact_match(query, speaker.code, name),
    }


def serialize_admin_user(user, query=""):
    name = user.get_display_name()
    return {
        "type": "user.admin",
        "name": _("User") + f" {name}",
        "email": user.email,
        "url": user.orga_urls.admin,
        "exact": is_exact_match(query, user.code, user.email, name),
    }


@scopes_disabled()
def nav_typeahead(request):
    organiser = request.GET.get("organiser")
    query = json.dumps(str(request.GET.get("query", "")))[1:-1]
    page = 1
    with suppress(ValueError):
        page = int(request.GET.get("page", "1"))

    qs_events = (
        request.user.get_events_with_any_permission()
        .filter(
            Q(name__icontains=query)
            | Q(slug__icontains=query)
            | Q(custom_domain__icontains=query)
            | Q(organiser__name__icontains=query)
            | Q(organiser__slug__icontains=query)
        )
        .select_related("organiser")
        .order_by("-date_from")
    )

    if not query:
        events = []
        for event in qs_events[:6]:
            serialized = serialize_event(event)
            serialized.pop("exact", None)
            events.append(serialized)
        return JsonResponse(
            {
                "results": events[:5],
                "has_more_events": len(events) > 5,
                "pagination": {"more": False},
            }
        )

    show_user = (
        request.user.email and query.lower() in request.user.email.lower()
    ) or (request.user.name and query.lower() in request.user.name.lower())

    qs_orga = (
        Organiser.objects.filter(
            pk__in=request.user.teams.values_list("organiser", flat=True)
        )
        .annotate(n_events=Count("events"))
        .order_by("-n_events")
    )
    if organiser and show_user:
        qs_orga = qs_orga.filter(
            Q(name__icontains=query) | Q(slug__icontains=query) | Q(pk=organiser)
        )
    else:
        qs_orga = qs_orga.filter(Q(name__icontains=query) | Q(slug__icontains=query))

    if organiser:
        organiser = qs_orga.filter(pk=organiser).first()

    qs_submissions = Submission.objects.none()
    qs_speakers = SpeakerProfile.objects.none()
    if len(query) >= 3:
        # Submission search is restricted to events the user can change
        # submissions on. Reviewer events are intentionally excluded, since
        # track-limited reviewers must not see submissions outside their
        # tracks and the typeahead does not filter by track.
        submission_events = request.user.get_events_for_permission(
            can_change_submissions=True
        )
        if submission_events:
            qs_submissions = (
                Submission.objects.filter(
                    Q(title__icontains=query) | Q(code__istartswith=query),
                    event__in=submission_events,
                )
                .select_related("event")
                .order_by()
            )

        # Speaker search uses the same access logic as the organiser-level
        # speaker list, which includes reviewer events when the user has
        # explicit speakerprofile listing permission and skips track-limited
        # reviewer teams. The helper returns a subquery-only queryset; we let
        # it embed lazily into ``event__in`` rather than evaluating it here.
        qs_speakers = (
            SpeakerProfile.objects.filter(
                Q(name__icontains=query)
                | Q(user__name__icontains=query)
                | Q(user__email__iexact=query)
                | Q(user__code__istartswith=query)
                | Q(code__istartswith=query),
                event__in=speaker_access_events_for_user(user=request.user),
            )
            .annotate(
                has_submission=Exists(
                    Submission.objects.filter(
                        event=OuterRef("event"), speakers=OuterRef("pk")
                    )
                )
            )
            .filter(has_submission=True)
            .select_related("event")
            .order_by()
        )

    qs_users = User.objects.none()
    if request.user.is_administrator:
        qs_users = User.objects.filter(
            Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(code__istartswith=query)
        ).order_by("email")

    pagesize = 20
    offset = (page - 1) * pagesize
    results = (
        ([serialize_user(request.user)] if show_user else [])
        + [serialize_orga(e, query) for e in qs_orga[offset : offset + pagesize]]
        + [serialize_event(e, query) for e in qs_events[offset : offset + pagesize]]
        + [
            serialize_submission(e, query)
            for e in qs_submissions[offset : offset + pagesize]
        ]
        + [serialize_admin_user(e, query) for e in qs_users[offset : offset + pagesize]]
        + [serialize_speaker(e, query) for e in qs_speakers[offset : offset + pagesize]]
    )

    if show_user and organiser:
        current_organiser = serialize_orga(organiser, query)
        if current_organiser in results:
            results.remove(current_organiser)
        results.insert(1, current_organiser)

    results.sort(key=lambda result: not result.get("exact"))
    for result in results:
        result.pop("exact", None)

    total = (
        qs_orga.count()
        + qs_events.count()
        + qs_submissions.count()
        + qs_users.count()
        + qs_speakers.count()
    )
    doc = {"results": results, "pagination": {"more": total >= (offset + pagesize)}}
    return JsonResponse(doc)
