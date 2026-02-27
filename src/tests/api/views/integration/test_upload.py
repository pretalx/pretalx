import pytest
from django.core.files.base import ContentFile

from pretalx.common.models.file import CachedFile

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_upload_pdf_creates_cached_file(client, orga_token):
    """Uploading a valid PDF creates a CachedFile and returns file:PK identifier."""
    assert CachedFile.objects.count() == 0

    response = client.post(
        "/api/upload/",
        data={"name": "file.pdf", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Authorization": f"Token {orga_token.token}",
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


@pytest.mark.django_db
def test_upload_image_creates_cached_file(client, orga_token, make_image):
    """Uploading a valid PNG image creates a CachedFile."""
    image = make_image("avatar.png")

    response = client.post(
        "/api/upload/",
        data=image.read(),
        content_type="image/png",
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Content-Disposition": 'attachment; filename="avatar.png"',
        },
    )

    assert response.status_code == 201, response.data
    assert response.data["id"].startswith("file:")
    assert CachedFile.objects.count() == 1


@pytest.mark.django_db
def test_upload_extension_mismatch_returns_400(client, orga_token):
    """File with extension not matching content type is rejected."""
    response = client.post(
        "/api/upload/",
        data={"name": "file.png", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Content-Disposition": 'attachment; filename="file.png"',
            "Content-Type": "application/pdf",
        },
    )

    assert response.status_code == 400
    assert response.data == [
        'File name "file.png" has an invalid extension for type "application/pdf"'
    ]


@pytest.mark.django_db
def test_upload_disallowed_content_type_returns_400(client, orga_token):
    """Files with unsupported content types are rejected."""
    response = client.post(
        "/api/upload/",
        data={"name": "file.bin", "file_field": ContentFile(b"binary content")},
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Content-Disposition": 'attachment; filename="file.bin"',
            "Content-Type": "application/octet-stream",
        },
    )

    assert response.status_code == 400
    assert "Content type is not allowed" in str(response.data)


@pytest.mark.django_db
def test_upload_no_file_returns_400(client, orga_token):
    """Request without Content-Disposition (no filename) returns 400."""
    response = client.post(
        "/api/upload/",
        data=b"",
        content_type="application/pdf",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 400
    assert "No file" in str(response.data)


@pytest.mark.django_db
def test_upload_invalid_image_returns_400(client, orga_token):
    """Uploading a file with image content type but corrupt data returns 400."""
    response = client.post(
        "/api/upload/",
        data=b"this is not a valid png image",
        content_type="image/png",
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Content-Disposition": 'attachment; filename="bad.png"',
        },
    )

    assert response.status_code == 400
    assert CachedFile.objects.count() == 0


@pytest.mark.django_db
def test_upload_unauthenticated_returns_401(client):
    """Unauthenticated upload requests are rejected with 401."""
    response = client.post(
        "/api/upload/",
        data={"name": "file.pdf", "file_field": ContentFile(b"fake pdf content")},
        headers={
            "Content-Disposition": 'attachment; filename="file.pdf"',
            "Content-Type": "application/pdf",
        },
    )

    assert response.status_code == 401
