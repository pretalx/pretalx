# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


# drf_spectacular adds a ton of startup time by loading rest_framework.test,
# which loads django.test, which loads all of jinja2.
# So we make drf_spectacular optional, and when it's not installed, we
# provide stubs


class OpenApiTypes:
    STR = None
    INT = None


def empty_method(*args, **kwargs):
    pass


def empty_wrapper(*outer_args, **outer_kwargs):
    def decorator(f):
        return f

    return decorator


extend_schema_serializer = empty_wrapper
extend_schema_field = empty_wrapper
extend_schema = empty_wrapper
extend_schema_view = empty_wrapper
OpenApiExample = empty_method
OpenApiResponse = empty_method
OpenApiParameter = empty_method
OpenApiParameter.QUERY = None
OpenApiParameter.PATH = None
