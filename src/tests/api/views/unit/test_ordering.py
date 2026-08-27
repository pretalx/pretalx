# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.urls import default_router, event_router, organiser_router
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = pytest.mark.unit


def _paginated_viewsets():
    for router in (default_router, event_router, organiser_router):
        for _prefix, viewset, basename in router.registry:
            if viewset.pagination_class is None:
                continue
            yield pytest.param(viewset, id=basename)


def test_paginated_viewset_discovery_finds_every_known_endpoint():
    # Make sure our tests do not break in the future
    assert len(list(_paginated_viewsets())) >= 10


def _first_ordering_field(viewset):
    fields = getattr(viewset, "ordering_fields", None) or ()
    return fields[0] if isinstance(fields, (list, tuple)) and fields else "id"


@pytest.mark.django_db
@pytest.mark.parametrize("viewset", list(_paginated_viewsets()))
def test_paginated_api_endpoints_are_totally_ordered_when_sorted(viewset, event):
    user = make_orga_user(event, is_reviewer=True)
    request = make_api_request(
        event=event,
        user=user,
        organiser=event.organiser,
        data={"o": _first_ordering_field(viewset)},
    )
    view = make_view(viewset, request)
    view.action = "list"

    queryset = view.filter_queryset(view.get_queryset())

    assert queryset.totally_ordered


@pytest.mark.django_db
@pytest.mark.parametrize("viewset", list(_paginated_viewsets()))
def test_paginated_api_endpoints_are_totally_ordered(viewset, event):
    user = make_orga_user(event, is_reviewer=True)
    request = make_api_request(event=event, user=user, organiser=event.organiser)
    view = make_view(viewset, request)
    view.action = "list"

    queryset = view.filter_queryset(view.get_queryset())

    assert queryset.totally_ordered
