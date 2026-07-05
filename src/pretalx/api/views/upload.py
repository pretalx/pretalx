# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.timezone import now
from rest_framework import permissions, serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView

from pretalx.api.documentation import (
    OpenApiExample,
    extend_schema,
    extend_schema_serializer,
)
from pretalx.common.files import DOCUMENT_UPLOAD_TYPES, IMAGE_UPLOAD_TYPES
from pretalx.common.image import validate_image
from pretalx.common.models import CachedFile


@extend_schema_serializer(examples=[OpenApiExample("", value={"id": "file:1234-5678"})])
class FileResponseSerializer(serializers.Serializer):
    """Serializer for file upload response."""

    id = serializers.CharField(help_text="Cached file identifier")


class UploadView(APIView):
    parser_classes = [FileUploadParser]
    permission_classes = [permissions.IsAuthenticated]
    allowed_types = DOCUMENT_UPLOAD_TYPES

    @extend_schema(
        operation_id="File upload",
        description="Upload a file (image, PDF or office document) for temporary "
        "storage. Allowed file types match the web interface: images (PNG, JPEG, "
        "GIF, WebP, BMP, TIFF), PDF, office documents (DOC, DOCX, XLS, XLSX, PPT, "
        "PPTX, ODT, ODS, ODP, RTF, TXT, CSV), and ZIP archives.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        },
        responses={
            201: FileResponseSerializer,
            400: {"type": "object", "description": "Validation error"},
        },
        tags=["file-uploads"],
    )
    def post(self, request):
        if not request.auth.has_any_write_permission():
            raise PermissionDenied
        file_obj = request.data.get("file")
        if not file_obj:
            raise ValidationError("No file has been submitted.")
        content_type = file_obj.content_type.split(";")[0]  # ignore e.g. "; charset=…"
        if not (allowed_extensions := self.allowed_types.get(content_type)):
            raise ValidationError("Content type is not allowed.")
        if not any(file_obj.name.endswith(ext) for ext in allowed_extensions):
            raise ValidationError(
                f'File name "{file_obj.name}" has an invalid extension for type "{content_type}"'
            )

        if content_type in IMAGE_UPLOAD_TYPES:
            try:
                validate_image(file_obj)
            except DjangoValidationError as e:
                raise ValidationError(e.message) from None

        cf = CachedFile.objects.create(
            expires=now() + datetime.timedelta(days=1),
            timestamp=now(),
            filename=file_obj.name,
            content_type=content_type,
            session_key=f"api-upload-{request.auth.token}",
        )
        cf.file.save(file_obj.name, file_obj, save=False)
        cf.save(update_fields=("file",))
        return Response({"id": f"file:{cf.pk}"}, status=201)
