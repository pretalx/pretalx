# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.tables import PretalxTable
from pretalx.common.tables.filters import BooleanFilter, FilterContext, TableFilterSet
from pretalx.submission.models import Submission
from tests.factories.event import EventFactory
from tests.factories.submission import SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def featured_filters(context):
    return [BooleanFilter(name="is_featured", label="Featured")]


class FilteredTable(PretalxTable):
    filters = staticmethod(featured_filters)

    class Meta:
        model = Submission
        fields = ()


class ModellessTable(PretalxTable):
    pass


def test_declared_filters_are_built_fresh_and_bound_to_the_context():
    context = FilterContext(event="sentinel")

    filterset = TableFilterSet(FilteredTable.get_filters(context), context=context)

    assert [f.name for f in filterset.filters.values()] == ["is_featured"]
    assert filterset.filters["is_featured"].event == "sentinel"
    assert (
        FilteredTable.get_filters(FilterContext())[0]
        is not FilteredTable.get_filters(FilterContext())[0]
    )


def test_a_table_without_filters_has_none():
    assert ModellessTable.get_filters(FilterContext()) == []


def test_table_filters_narrow_the_queryset():
    event = EventFactory()
    featured = SubmissionFactory(event=event, is_featured=True)
    SubmissionFactory(event=event, is_featured=False)
    context = FilterContext(event=event)

    filterset = TableFilterSet(
        FilteredTable.get_filters(context),
        data=QueryDict("is_featured=true"),
        context=context,
    )

    assert list(filterset.filter(event.submissions.all())) == [featured]


def test_an_unpaginated_table_counts_its_own_rows():
    event = EventFactory()
    SubmissionFactory(event=event)
    SubmissionFactory(event=event)
    table = FilteredTable(event.submissions.all())

    assert table.filtered_count == 2
