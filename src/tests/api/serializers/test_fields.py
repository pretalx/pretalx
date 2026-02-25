import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django_scopes import scopes_disabled
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretalx.api.serializers.fields import UploadedFileField
from tests.factories import CachedFileFactory, UserApiTokenFactory

pytestmark = pytest.mark.unit

rf = RequestFactory()


class _FileFieldWrapper(serializers.Serializer):
    """Minimal serializer wrapping UploadedFileField so it gets DRF context."""

    file = UploadedFileField()


class _FileFieldWrapperTypeOnly(serializers.Serializer):
    file = UploadedFileField(allowed_types=["image/png"])


class _FileFieldWrapperSizeOnly(serializers.Serializer):
    file = UploadedFileField(max_size=100)


@pytest.mark.django_db
def test_uploaded_file_field_to_internal_value_returns_file():
    api_token = UserApiTokenFactory()
    uploaded = SimpleUploadedFile("test.txt", b"file content")
    with scopes_disabled():
        cf = CachedFileFactory(
            session_key=f"api-upload-{api_token.token}", file=uploaded
        )
    request = rf.get("/")
    request.auth = api_token
    wrapper = _FileFieldWrapper(context={"request": request})
    field = wrapper.fields["file"]

    result = field.to_internal_value(f"file:{cf.pk}")
    assert result.read() == b"file content"


@pytest.mark.django_db
def test_uploaded_file_field_to_internal_value_not_found_wrong_id():
    api_token = UserApiTokenFactory()
    request = rf.get("/")
    request.auth = api_token
    wrapper = _FileFieldWrapper(context={"request": request})
    field = wrapper.fields["file"]

    with pytest.raises(ValidationError, match="not found"):
        field.to_internal_value("file:00000000-0000-0000-0000-000000000000")


@pytest.mark.django_db
def test_uploaded_file_field_to_internal_value_not_found_wrong_session():
    """A CachedFile with a different session key is not returned."""
    api_token = UserApiTokenFactory()
    uploaded = SimpleUploadedFile("test.txt", b"content")
    with scopes_disabled():
        cf = CachedFileFactory(session_key="api-upload-other-token", file=uploaded)
    request = rf.get("/")
    request.auth = api_token
    wrapper = _FileFieldWrapper(context={"request": request})
    field = wrapper.fields["file"]

    with pytest.raises(ValidationError, match="not found"):
        field.to_internal_value(f"file:{cf.pk}")


@pytest.mark.django_db
def test_uploaded_file_field_to_internal_value_rejects_wrong_type():
    api_token = UserApiTokenFactory()
    uploaded = SimpleUploadedFile(
        "test.pdf", b"pdf content", content_type="application/pdf"
    )
    with scopes_disabled():
        cf = CachedFileFactory(
            session_key=f"api-upload-{api_token.token}",
            file=uploaded,
            content_type="application/pdf",
        )
    request = rf.get("/")
    request.auth = api_token
    wrapper = _FileFieldWrapperTypeOnly(context={"request": request})
    field = wrapper.fields["file"]

    with pytest.raises(ValidationError, match="file type"):
        field.to_internal_value(f"file:{cf.pk}")


@pytest.mark.django_db
def test_uploaded_file_field_to_internal_value_rejects_oversized():
    api_token = UserApiTokenFactory()
    uploaded = SimpleUploadedFile("big.txt", b"x" * 200)
    with scopes_disabled():
        cf = CachedFileFactory(
            session_key=f"api-upload-{api_token.token}", file=uploaded
        )
    request = rf.get("/")
    request.auth = api_token
    wrapper = _FileFieldWrapperSizeOnly(context={"request": request})
    field = wrapper.fields["file"]

    with pytest.raises(ValidationError, match="too large"):
        field.to_internal_value(f"file:{cf.pk}")


def test_uploaded_file_field_to_representation_returns_none_for_falsy():
    request = rf.get("/")
    wrapper = _FileFieldWrapper(context={"request": request})
    field = wrapper.fields["file"]

    assert field.to_representation(None) is None
    assert field.to_representation("") is None


def test_uploaded_file_field_to_representation_returns_none_without_url():
    """An object without a .url attribute results in None."""
    request = rf.get("/")
    wrapper = _FileFieldWrapper(context={"request": request})
    field = wrapper.fields["file"]

    assert field.to_representation(object()) is None


@pytest.mark.django_db
def test_uploaded_file_field_to_representation_returns_none_without_request():
    uploaded = SimpleUploadedFile("test.txt", b"content")
    with scopes_disabled():
        cf = CachedFileFactory(file=uploaded)
    wrapper = _FileFieldWrapper(context={})
    field = wrapper.fields["file"]

    assert field.to_representation(cf.file) is None


@pytest.mark.django_db
def test_uploaded_file_field_to_representation_returns_absolute_uri():
    uploaded = SimpleUploadedFile("test.txt", b"content")
    with scopes_disabled():
        cf = CachedFileFactory(file=uploaded)
    request = rf.get("/api/test/")
    wrapper = _FileFieldWrapper(context={"request": request})
    field = wrapper.fields["file"]

    result = field.to_representation(cf.file)
    assert result == f"http://testserver{cf.file.url}"
