# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.functional import cached_property
from rest_flex_fields import is_expanded
from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.response import Response

from pretalx.api.documentation import extend_schema
from pretalx.api.serializers.log import ActivityLogSerializer
from pretalx.api.versions import get_api_version_from_request, get_serializer_by_version


class ApiVersionException(exceptions.APIException):
    status_code = 400
    default_detail = "API version not supported."
    default_code = "invalid_version"


class PretalxViewSetMixin:
    endpoint = None
    logtype_map = {
        "create": ".create",
        "update": ".update",
        "partial_update": ".update",
    }

    @cached_property
    def api_version(self):
        try:
            return get_api_version_from_request(self.request)
        except Exception:
            raise ApiVersionException()

    def get_versioned_serializer(self, name):
        try:
            return get_serializer_by_version(name, self.api_version)
        except KeyError:
            raise ApiVersionException()

    def get_serializer_class(self):
        if hasattr(self, "get_unversioned_serializer_class"):
            base_class = self.get_unversioned_serializer_class()
        elif hasattr(self, "serializer_class"):
            base_class = self.serializer_class
        return self.get_versioned_serializer(base_class.__name__)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        locale = self.request.GET.get("lang")
        if self.event and locale and locale in self.event.locales:
            context["override_locale"] = locale
        return context

    def perform_create(self, serializer):
        super().perform_create(serializer)
        serializer.instance.log_action(".create", person=self.request.user, orga=True)

    def perform_update(self, serializer):
        old_data = None
        if hasattr(serializer.instance, "_get_instance_data"):
            old_data = serializer.instance._get_instance_data()

        super().perform_update(serializer)

        new_data = None
        if hasattr(serializer.instance, "_get_instance_data"):
            new_data = serializer.instance._get_instance_data()

        log_kwargs = {"person": self.request.user, "orga": True}
        if old_data is not None and new_data is not None:
            log_kwargs["old_data"] = old_data
            log_kwargs["new_data"] = new_data

        serializer.instance.log_action(".update", **log_kwargs)

    @cached_property
    def event(self):
        # request.event is not present when building API docs
        return getattr(self.request, "event", None)

    def has_perm(self, permission, obj=None):
        model = getattr(self, "model", None) or self.queryset.model
        permission_name = model.get_perm(permission)
        return self.request.user.has_perm(permission_name, obj or self.event)

    def check_expanded_fields(self, *args):
        return [arg for arg in args if is_expanded(self.request, arg)]


class ActivityLogMixin:

    @extend_schema(
        summary="Object changelog",
        description="Changelog entries related to this object.",
        responses=ActivityLogSerializer(many=True),
    )
    @action(detail=True, methods=["GET"], url_path="log")
    def log(self, request, **kwargs):
        """Return log entries for this object."""

        obj = self.get_object()

        if not hasattr(obj, "logged_actions"):
            raise exceptions.MethodNotAllowed(method="GET")

        logs = obj.logged_actions().select_related("person", "event")
        page = self.paginate_queryset(logs)
        if page is not None:
            serializer = ActivityLogSerializer(
                page, many=True, context=self.get_serializer_context()
            )
            return self.get_paginated_response(serializer.data)

        serializer = ActivityLogSerializer(
            logs, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)
