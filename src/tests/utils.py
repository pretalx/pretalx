from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

_rf = RequestFactory()
_api_rf = APIRequestFactory()


def make_request(event, user=None, method="get", path="/", headers=None, **attrs):
    """Create a Django request for view unit tests.

    Sets ``event`` on the request.  ``user`` defaults to ``AnonymousUser``
    to match Django middleware behaviour; pass a real user for authenticated
    tests.  Any extra keyword arguments are set as request attributes
    (e.g. ``resolver_match``)."""
    request = getattr(_rf, method)(path, **({"headers": headers} if headers else {}))
    request.event = event
    request.user = user if user is not None else AnonymousUser()
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
