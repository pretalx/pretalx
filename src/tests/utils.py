from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from tests.factories import TeamFactory, UserFactory

_rf = RequestFactory()
_api_rf = APIRequestFactory()


class SimpleSession(dict):
    """Minimal dict-like session for unit tests.

    Supports the ``modified`` flag that Django's session interface exposes,
    without pulling in the full session machinery."""

    modified = False


def make_request(event, user=None, method="get", path="/", headers=None, **attrs):
    """Create a Django request for view unit tests.

    Sets ``event`` on the request.  ``user`` defaults to ``AnonymousUser``
    to match Django middleware behaviour; pass a real user for authenticated
    tests.  A minimal ``session`` dict is attached by default — pass
    ``session=…`` in *attrs* to override.  Any extra keyword arguments are
    set as request attributes (e.g. ``resolver_match``)."""
    request = getattr(_rf, method)(path, **({"headers": headers} if headers else {}))
    request.event = event
    request.user = user if user is not None else AnonymousUser()
    if "session" not in attrs:
        request.session = SimpleSession()
    for key, value in attrs.items():
        setattr(request, key, value)
    return request


def make_api_request(event=None, user=None, auth=None, path="/", data=None, **attrs):
    """Create a DRF Request for serializer and API unit tests.

    Sets event, user, auth, and any additional keyword arguments (e.g. organiser)
    as attributes on the underlying Django request.
    """
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
    """Create a user with organiser access.

    When *teams* is given the user is added to each existing team and no new
    team is created (``event`` and ``**team_kwargs`` are ignored).

    Otherwise a new team is created on ``event.organiser`` with
    ``all_events=True`` by default.  Pass keyword arguments to override or
    extend TeamFactory fields, e.g.
    ``make_orga_user(event, can_change_submissions=True)``.
    """
    user = UserFactory()
    if teams is not None:
        for team in teams:
            team.members.add(user)
    else:
        team_kwargs.setdefault("all_events", True)
        team = TeamFactory(organiser=event.organiser, **team_kwargs)
        team.members.add(user)
    return user


def refresh(instance, **updates):
    """Return a fresh instance from the database, clearing cached_property values.

    Optionally applies field updates and saves before re-fetching.

    Usage::

        event = refresh(event)  # just re-fetch
        event = refresh(event, is_public=True, date_from=tomorrow)  # update + re-fetch
    """
    if updates:
        for attr, value in updates.items():
            setattr(instance, attr, value)
        instance.save()
    return type(instance).objects.get(pk=instance.pk)
