import pytest
from django.test import RequestFactory

from pretalx.api.pagination import LimitOffsetPagination, PageNumberPagination
from pretalx.event.models import Event
from tests.utils import make_api_request

pytestmark = pytest.mark.unit

rf = RequestFactory()


@pytest.mark.parametrize(
    ("params", "expected"),
    (
        ({"limit": "10", "offset": "0"}, True),
        ({"limit": "10"}, False),
        ({"offset": "0"}, False),
        ({}, False),
    ),
    ids=["both_present", "missing_offset", "missing_limit", "no_params"],
)
def test_page_number_pagination_is_limit_offset(params, expected):
    request = rf.get("/", params)
    paginator = PageNumberPagination()
    paginator.request = request
    assert bool(paginator.is_limit_offset) == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("params", "expect_limit_offset"),
    (({"limit": "10", "offset": "0"}, True), ({"page": "1"}, False)),
    ids=["limit_offset", "page_number"],
)
def test_page_number_pagination_paginate_queryset(
    params, expect_limit_offset, settings
):
    """Delegates to LimitOffsetPagination when limit+offset are present,
    otherwise uses standard page-number pagination."""
    settings.MAX_PAGINATION_LIMIT = 100
    request = make_api_request(data=params)
    paginator = PageNumberPagination()

    result = paginator.paginate_queryset(Event.objects.none(), request)

    assert result == []
    assert bool(paginator.is_limit_offset) == expect_limit_offset


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    ({"limit": "10", "offset": "0"}, {"page": "1"}),
    ids=["limit_offset", "page_number"],
)
def test_page_number_pagination_get_paginated_response(params, settings):
    """Both pagination modes include count, next, and previous in the response."""
    settings.MAX_PAGINATION_LIMIT = 100
    request = make_api_request(data=params)
    paginator = PageNumberPagination()
    paginator.paginate_queryset(Event.objects.none(), request)

    response = paginator.get_paginated_response([])

    assert "count" in response.data
    assert "next" in response.data
    assert "previous" in response.data


def test_page_number_pagination_limit_offset_paginator_is_cached():
    """The limit_offset_paginator property returns the same instance on repeated access."""
    paginator = PageNumberPagination()
    first = paginator.limit_offset_paginator
    second = paginator.limit_offset_paginator
    assert first is second
    assert isinstance(first, LimitOffsetPagination)
