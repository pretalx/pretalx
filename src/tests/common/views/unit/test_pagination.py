# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.paginator import (
    EmptyPage,
    PageNotAnInteger,
    Paginator,
    UnorderedObjectListWarning,
)
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import get_resolver
from django_scopes import scope, scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.common.views.generic import OrgaTableMixin
from pretalx.common.views.mixins import PaginationMixin
from pretalx.common.views.pagination import (
    MAX_DATABASE_INTEGER,
    LargeResultSetPaginator,
)
from tests.factories import ActivityLogFactory, EventFactory, SpeakerRoleFactory
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


def test_paginator_page_returns_only_page_size_objects():
    paginator = LargeResultSetPaginator(list(range(10)), 3)

    page = paginator.page(2)

    assert list(page) == [3, 4, 5]
    assert len(page) == 3
    assert page[0] == 3
    assert page.number == 2
    assert repr(page) == "<Page 2>"


def test_paginator_has_no_count_or_num_pages():
    paginator = LargeResultSetPaginator(list(range(10)), 3)

    assert paginator.count is None
    with pytest.raises(Http404):
        paginator.num_pages  # noqa: B018 -- property raises on access


@pytest.mark.parametrize(
    ("total", "number", "has_previous", "has_next"),
    (
        (10, 1, False, True),
        (10, 2, True, True),
        (10, 4, True, False),
        (9, 3, True, False),
        (3, 1, False, False),
        (0, 1, False, False),
    ),
)
def test_paginator_page_navigation(total, number, has_previous, has_next):
    paginator = LargeResultSetPaginator(list(range(total)), 3)

    page = paginator.page(number)

    assert page.has_previous() is has_previous
    assert page.has_next() is has_next
    assert page.has_other_pages() is (has_previous or has_next)


def test_paginator_page_numbers_of_neighbouring_pages():
    page = LargeResultSetPaginator(list(range(10)), 3).page(2)

    assert page.next_page_number() == 3
    assert page.previous_page_number() == 1


def test_paginator_first_page_has_no_previous_page_number():
    page = LargeResultSetPaginator(list(range(10)), 3).page(1)

    with pytest.raises(EmptyPage):
        page.previous_page_number()


@pytest.mark.parametrize(
    ("total", "number", "start_index", "end_index"),
    ((10, 1, 1, 3), (10, 4, 10, 10), (0, 1, 0, 0)),
)
def test_paginator_page_indices(total, number, start_index, end_index):
    paginator = LargeResultSetPaginator(list(range(total)), 3)

    page = paginator.page(number)

    assert page.start_index() == start_index
    assert page.end_index() == end_index


@pytest.mark.parametrize("number", ("a", None))
def test_paginator_rejects_non_integer_page(number):
    paginator = LargeResultSetPaginator(list(range(10)), 3)

    with pytest.raises(PageNotAnInteger):
        paginator.page(number)


@pytest.mark.parametrize("number", (0, -1))
def test_paginator_rejects_page_below_one(number):
    paginator = LargeResultSetPaginator(list(range(10)), 3)

    with pytest.raises(EmptyPage):
        paginator.page(number)


@pytest.mark.parametrize("number", (5, 9999))
def test_paginator_rejects_page_past_the_end(number):
    paginator = LargeResultSetPaginator(list(range(10)), 3)

    with pytest.raises(EmptyPage):
        paginator.page(number)


@pytest.mark.django_db
@pytest.mark.parametrize("per_page", (25, 200))
def test_paginator_rejects_page_beyond_upper_bound(per_page, django_assert_num_queries):
    with scopes_disabled():
        paginator = LargeResultSetPaginator(ActivityLog.objects.all(), per_page)
    bound = paginator.max_page_number

    assert (bound - 1) * per_page <= MAX_DATABASE_INTEGER < bound * per_page

    for number in (bound + 1, 99999999999999999999):
        with django_assert_num_queries(0), pytest.raises(EmptyPage):
            paginator.page(number)


def test_paginator_allows_empty_first_page():
    paginator = LargeResultSetPaginator([], 3)

    page = paginator.page(1)

    assert list(page) == []


def render_pagination(page, **context):
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    return render_to_string(
        "common/includes/pagination.html",
        {"page_obj": page, **context},
        request=request,
    )


@pytest.mark.parametrize(
    ("total", "has_next_link"),
    ((10, True), (6, False)),
    ids=("more-pages", "last-page"),
)
def test_pagination_widget_without_count_shows_page_number_and_links(
    total, has_next_link
):
    page = LargeResultSetPaginator(list(range(total)), 3).page(2)

    content = render_pagination(page, pagination_sizes=[50, 100])

    assert "Page 2" in content
    assert "elements" not in content
    assert "?page=1" in content
    assert ("?page=3" in content) is has_next_link
    assert "Show per page" in content


@pytest.mark.parametrize("total", (0, 3), ids=("empty", "single-page"))
def test_pagination_widget_without_count_is_empty_without_other_pages(total):
    page = LargeResultSetPaginator(list(range(total)), 3).page(1)

    assert render_pagination(page, pagination_sizes=[50, 100]).strip() == ""


def test_pagination_widget_with_count_still_shows_totals_and_page_sizes():
    page = Paginator(list(range(80)), 5).page(1)

    content = render_pagination(page, pagination_sizes=[50, 100])

    assert "Page 1 of 16 (80 elements)" in content
    assert "Show per page" in content
    assert "?page_size=50&amp;page=1" in content


@pytest.mark.django_db
def test_paginator_warns_about_unordered_object_list():
    with scopes_disabled():
        queryset = ActivityLog.objects.order_by()

    with pytest.warns(UnorderedObjectListWarning):
        LargeResultSetPaginator(queryset, 3)


@pytest.mark.django_db
def test_paginator_does_not_count_the_queryset(django_assert_num_queries):
    with scopes_disabled():
        event = EventFactory()
        ActivityLogFactory.create_batch(4, event=event)
        queryset = ActivityLog.objects.filter(event=event)

        paginator = LargeResultSetPaginator(queryset, 2)
        with django_assert_num_queries(1):
            page = paginator.page(1)
            assert len(page.object_list) == 2
            assert page.has_next() is True


@pytest.mark.django_db
@pytest.mark.parametrize(("item_count", "shows_nav"), ((1, False), (4, True)))
def test_pagination_widget_without_count_does_not_query(
    item_count, shows_nav, django_assert_num_queries
):
    with scopes_disabled():
        event = EventFactory()
        ActivityLogFactory.create_batch(item_count, event=event)
        page = LargeResultSetPaginator(ActivityLog.objects.filter(event=event), 3).page(
            1
        )

        with django_assert_num_queries(0):
            content = render_pagination(page, pagination_sizes=[50, 100])

    assert ("Page 1" in content) is shows_nav
    assert ("Show per page" in content) is shows_nav


def _paginates(view_class):
    if getattr(view_class, "table_pagination", None) is False:
        return False
    if issubclass(view_class, (PaginationMixin, OrgaTableMixin)):
        return True
    return bool(getattr(view_class, "paginate_by", None))


def _paginated_view_classes():
    found = {}

    def walk(patterns):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern.url_patterns)
                continue
            view_class = getattr(pattern.callback, "view_class", None)
            if view_class is not None and _paginates(view_class):
                found[f"{view_class.__module__}.{view_class.__qualname__}"] = view_class

    walk(get_resolver().url_patterns)
    return [
        pytest.param(view_class, id=name) for name, view_class in sorted(found.items())
    ]


def test_paginated_view_discovery_finds_every_known_surface():
    # Make sure our tests do not break in the future
    assert len(_paginated_view_classes()) >= 10


@pytest.mark.django_db
@pytest.mark.parametrize("view_class", _paginated_view_classes())
def test_paginated_views_are_totally_ordered(view_class, event):
    with scope(event=event):
        submission = SpeakerRoleFactory(
            submission__event=event, speaker__event=event
        ).submission
        user = make_orga_user(event, is_reviewer=True)
        user.is_administrator = True
        user.save()
        request = make_request(event, user, organiser=event.organiser)
        view = make_view(view_class, request, code=submission.code)
        view.action = "list"

        assert view.get_queryset().totally_ordered
