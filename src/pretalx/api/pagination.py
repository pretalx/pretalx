# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from rest_framework import pagination


class PageNumberPagination(pagination.PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = settings.MAX_PAGINATION_LIMIT
