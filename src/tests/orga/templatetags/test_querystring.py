import types

import pytest
from django.test import RequestFactory

from pretalx.orga.templatetags.querystring import django_querystring

pytestmark = pytest.mark.unit


def test_django_querystring_delegates_to_builtin():
    """django_querystring wraps Django's built-in querystring tag, producing
    a query string that includes both existing GET params and new kwargs."""
    rf = RequestFactory()
    request = rf.get("/", {"existing": "val"})
    context = types.SimpleNamespace(request=request)

    result = django_querystring(context, page=3, sort="name")

    assert "page=3" in result
    assert "sort=name" in result
    assert "existing=val" in result
