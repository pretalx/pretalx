import pytest
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import IsAuthenticated

from pretalx.api.views.upload import UploadView

pytestmark = pytest.mark.unit


def test_upload_view_allowed_types():
    """UploadView.allowed_types covers PNG, JPEG, GIF, and PDF."""
    assert UploadView.allowed_types == {
        "image/png": [".png"],
        "image/jpeg": [".jpg", ".jpeg"],
        "image/gif": [".gif"],
        "application/pdf": [".pdf"],
    }


def test_upload_view_requires_authentication():
    """UploadView enforces IsAuthenticated permission."""
    assert any(issubclass(p, IsAuthenticated) for p in UploadView.permission_classes)


def test_upload_view_uses_file_upload_parser():
    """UploadView uses FileUploadParser."""
    assert any(issubclass(p, FileUploadParser) for p in UploadView.parser_classes)
