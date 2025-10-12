# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.http import HttpResponse
from django.views.decorators.cache import cache_page


@cache_page(3600)
def robots_txt(request):
    return HttpResponse(
        """User-agent: *
Disallow: /me/
Disallow: /locale/set*
Disallow: /orga/
Disallow: /download/
Disallow: /redirect/
Disallow: /api/
Disallow: /media/
""",
        content_type="text/plain",
    )
