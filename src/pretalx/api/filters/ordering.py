# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework import filters


class TiebreakerOrderingFilter(filters.OrderingFilter):
    """Ordering filter that always ends on the primary key to guarantee
    deterministic ordering."""

    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or ())
        opts = queryset.model._meta
        if not {"pk", opts.pk.name, opts.pk.attname} & {
            field.lstrip("-") for field in ordering
        }:
            ordering.append("pk")
        return ordering
