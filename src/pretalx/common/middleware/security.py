# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import BadRequest
from django.utils.deprecation import MiddlewareMixin


class RejectInvalidInputMiddleware(MiddlewareMixin):
    """
    Block requests containing null bytes in GET or POST params or URL paths.

    These requests fail later on database access, which clutters our error logs
    when a vulnerability spammer, sorry, scanner runs blindly against pretalx.
    """

    def process_request(self, request):
        if (
            "\x00" in request.path
            or "\x00" in request.META["QUERY_STRING"]
            or "%00" in request.META["QUERY_STRING"]
        ):
            raise BadRequest("Invalid characters in input.")

        # Multipart form data can contain legitimate null bytes, so we stick
        # to x-ww-form-urlencoded. PUT and PATCH do not populate request.POST,
        # so we would have to parse request.body. Scanners stick to GET and
        # POST most of the time, so that's not worth it for now.
        if (
            request.method == "POST"
            and request.content_type == "application/x-www-form-urlencoded"
            and any(
                "\x00" in item
                for key, value_list in request.POST.lists()
                for item in (key, *value_list)
            )
        ):
            raise BadRequest("Invalid characters in input.")
