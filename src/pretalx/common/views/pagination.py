# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.paginator import BasePaginator, EmptyPage, Page
from django.http import Http404

MAX_DATABASE_INTEGER = 2**63 - 1


class LargeResultSetPage(Page):
    """A page that does not know how many results exist in total."""

    def __init__(self, object_list, number, paginator, has_next=False):
        super().__init__(object_list, number, paginator)
        self._has_next = has_next

    def __repr__(self):
        return f"<Page {self.number}>"

    def has_next(self):
        return self._has_next

    def start_index(self):
        if not len(self.object_list):
            return 0
        return (self.paginator.per_page * (self.number - 1)) + 1

    def end_index(self):
        if not len(self.object_list):
            return 0
        return self.start_index() + len(self.object_list) - 1


class LargeResultSetPaginator(BasePaginator):
    """A paginator for result sets that are too large to COUNT(*)"""

    count = None

    @property
    def num_pages(self):
        # We do not know the number of items and therefore not the number
        # of pages either. Both MultipleObjectMixin (with ?page=last) and
        # django-tables2's RequestConfig (with its EmptyPage handling) fall
        # back to the max page number -- so we pass a 404 through to be safe.
        raise Http404

    @property
    def max_page_number(self):
        # Huge number, but not so huge as to cause errors; it's handled
        # via the regular out-of-range checks.
        return MAX_DATABASE_INTEGER // self.per_page + 1

    def validate_number(self, number):
        return self._validate_number(number, self.max_page_number)

    def page(self, number):
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        objects = list(self.object_list[bottom : bottom + self.per_page + 1])
        if not objects and number > 1:
            raise EmptyPage(self.error_messages["no_results"])
        has_next = len(objects) > self.per_page
        return self._get_page(objects[: self.per_page], number, self, has_next=has_next)

    def _get_page(self, *args, **kwargs):
        return LargeResultSetPage(*args, **kwargs)
