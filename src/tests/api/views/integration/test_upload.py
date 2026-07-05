# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.files.base import ContentFile

from pretalx.common.models.file import CachedFile

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_upload_pdf_creates_cached_file(client, orga_write_token):
    assert CachedFile.objects.count() == 0

    response = client.post(
        "/api/upload/",
        data={"name": "file.pdf", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": 'attachment; filename="file.pdf"',
            "Content-Type": "application/pdf",
        },
    )

    assert response.status_code == 201
    assert response.data["id"].startswith("file:")
    assert CachedFile.objects.count() == 1
    cf = CachedFile.objects.first()
    assert cf.filename == "file.pdf"
    assert cf.content_type == "application/pdf"


def test_upload_image_creates_cached_file(client, orga_write_token, make_image):
    image = make_image("avatar.png")

    response = client.post(
        "/api/upload/",
        data=image.read(),
        content_type="image/png",
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": 'attachment; filename="avatar.png"',
        },
    )

    assert response.status_code == 201, response.data
    assert response.data["id"].startswith("file:")
    assert CachedFile.objects.count() == 1


@pytest.mark.parametrize(
    ("filename", "content_type"),
    (("scan.bmp", "image/bmp"), ("scan.tiff", "image/tiff")),
    ids=("bmp", "tiff"),
)
def test_upload_document_image_type_skips_image_validation(
    client, orga_write_token, filename, content_type
):
    response = client.post(
        "/api/upload/",
        data={"name": filename, "file_field": ContentFile(b"fake image content")},
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        },
    )

    assert response.status_code == 201, response.data
    assert response.data["id"].startswith("file:")
    cf = CachedFile.objects.get()
    assert cf.filename == filename
    assert cf.content_type == content_type


def test_upload_extension_mismatch_returns_400(client, orga_write_token):
    response = client.post(
        "/api/upload/",
        data={"name": "file.png", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": 'attachment; filename="file.png"',
            "Content-Type": "application/pdf",
        },
    )

    assert response.status_code == 400
    assert response.data == [
        'File name "file.png" has an invalid extension for type "application/pdf"'
    ]


@pytest.mark.parametrize(
    ("filename", "content_type", "body"),
    (
        ("file.bin", "application/octet-stream", b"binary content"),
        ("evil.html", "text/html", b"<script>x</script>"),
    ),
    ids=("octet_stream", "active_content_html"),
)
def test_upload_disallowed_content_type_returns_400(
    client, orga_write_token, filename, content_type, body
):
    response = client.post(
        "/api/upload/",
        data={"name": filename, "file_field": ContentFile(body)},
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        },
    )

    assert response.status_code == 400
    assert "Content type is not allowed" in str(response.data)
    assert CachedFile.objects.count() == 0


def test_upload_no_file_returns_400(client, orga_write_token):
    response = client.post(
        "/api/upload/",
        data=b"",
        content_type="application/pdf",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "No file" in str(response.data)


def test_upload_invalid_image_returns_400(client, orga_write_token):
    response = client.post(
        "/api/upload/",
        data=b"this is not a valid png image",
        content_type="image/png",
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": 'attachment; filename="bad.png"',
        },
    )

    assert response.status_code == 400
    assert CachedFile.objects.count() == 0


def test_upload_unauthenticated_returns_401(client):
    response = client.post(
        "/api/upload/",
        data={"name": "file.pdf", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Content-Disposition": 'attachment; filename="file.pdf"',
            "Content-Type": "application/pdf",
        },
    )

    assert response.status_code == 401


def test_upload_read_only_token_returns_403(client, orga_read_token):
    response = client.post(
        "/api/upload/",
        data={"name": "file.pdf", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Authorization": f"Token {orga_read_token.token}",
            "Content-Disposition": 'attachment; filename="file.pdf"',
            "Content-Type": "application/pdf",
        },
    )

    assert response.status_code == 403
    assert CachedFile.objects.count() == 0
