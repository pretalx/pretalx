# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.submission.validators.resource import validate_resource_link_xor_file

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("link", "resource"),
    (("https://example.com", None), ("", SimpleUploadedFile("f", b"x"))),
    ids=("link_only", "file_only"),
)
def test_validate_resource_accepts_exactly_one(link, resource):
    validate_resource_link_xor_file(link=link, resource=resource)


@pytest.mark.parametrize(
    ("link", "resource", "match"),
    (
        ("https://example.com", SimpleUploadedFile("f", b"x"), "cannot do both"),
        ("", None, "provide a link or upload a file"),
    ),
    ids=("both", "neither"),
)
def test_validate_resource_rejects(link, resource, match):
    with pytest.raises(ValidationError, match=match):
        validate_resource_link_xor_file(link=link, resource=resource)
