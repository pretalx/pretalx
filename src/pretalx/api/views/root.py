# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from django.urls import reverse
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from pretalx.api.documentation import extend_schema
from pretalx.api.versions import CURRENT_VERSION


class RootUrlsSerializer(serializers.Serializer):
    events = serializers.URLField()


class RootSerializer(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField()
    api_version = serializers.CharField()
    urls = RootUrlsSerializer()


class RootView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="API Root",
        description="Returns a link to the REST API, as well as the pretalx and API versions.",
        tags=["root"],
        responses={200: RootSerializer},
    )
    def get(self, request):
        return Response(
            {
                "name": "pretalx",
                "version": settings.PRETALX_VERSION,
                "api_version": CURRENT_VERSION,
                "urls": {
                    "events": settings.SITE_URL + reverse("api:event-list"),
                },
            }
        )
