# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django_scopes import scope, scopes_disabled
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)

_rf = RequestFactory()
_api_rf = APIRequestFactory()


class SimpleSession(dict):
    modified = False


def make_request(event, user=None, method="get", path="/", headers=None, **attrs):
    """Create a Django request for view unit tests.

    Any extra keyword arguments are set as request attributes (e.g. ``resolver_match``)."""
    request = getattr(_rf, method)(path, **({"headers": headers} if headers else {}))
    request.event = event
    request.user = user if user is not None else AnonymousUser()
    if "session" not in attrs:
        request.session = SimpleSession()
    for key, value in attrs.items():
        setattr(request, key, value)
    return request


def make_api_request(event=None, user=None, auth=None, path="/", data=None, **attrs):
    """Create a DRF Request for serializer and API unit tests."""
    django_request = _api_rf.get(path, data or {})
    if event is not None:
        django_request.event = event
    for key, value in attrs.items():
        setattr(django_request, key, value)
    drf_request = Request(django_request)
    # Always set auth first: DRF's lazy authentication triggers on the first
    # access to .auth or .user and will overwrite both with defaults.  Setting
    # auth explicitly prevents _authenticate() from clobbering a user we set.
    drf_request.auth = auth
    if user is not None:
        drf_request.user = user
    return drf_request


def make_view(view_class, request, **kwargs):
    """Instantiate a view with request and kwargs, without dispatching."""
    view = view_class()
    view.request = request
    view.kwargs = kwargs
    return view


def make_orga_user(event=None, *, teams=None, **team_kwargs):
    """Create a user with organiser access."""
    user = UserFactory()
    if teams is not None:
        for team in teams:
            team.members.add(user)
    else:
        team_kwargs.setdefault("all_events", True)
        team = TeamFactory(organiser=event.organiser, **team_kwargs)
        team.members.add(user)
    return user


def make_published_schedule(event, item_count, *, version="v1"):
    """Create *item_count* confirmed talks (each with a speaker and visible
    slot) and freeze the WIP schedule.

    Returns the list of created submissions.  Useful for query-count tests
    where you need a released schedule with a controlled number of talks."""
    submissions = []
    with scopes_disabled():
        for i in range(item_count):
            submission = SubmissionFactory(
                event=event, state=SubmissionStates.CONFIRMED
            )
            speaker = SpeakerFactory(event=event)
            submission.speakers.add(speaker)
            TalkSlotFactory(
                submission=submission,
                is_visible=True,
                start=event.datetime_from + dt.timedelta(hours=i),
                end=event.datetime_from + dt.timedelta(hours=i + 1),
            )
            submissions.append(submission)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, version, notify_speakers=False)
    return submissions


def refresh(instance):
    """Return a fresh instance from the database, clearing cached_property values."""
    return type(instance).objects.get(pk=instance.pk)
