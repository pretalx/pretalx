# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.submission.validators.resource import validate_resource_link_xor_file

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("link", "resource", "messages"),
    (
        ("https://example.com", None, []),
        ("", SimpleUploadedFile("f", b"x"), []),
        (
            "https://example.com",
            SimpleUploadedFile("f", b"x"),
            ["Please either provide a link or upload a file, you cannot do both!"],
        ),
        ("", None, ["Please provide a link or upload a file!"]),
    ),
    ids=("link_only", "file_only", "both", "neither"),
)
def test_validate_resource_link_xor_file(link, resource, messages):
    try:
        validate_resource_link_xor_file(link=link, resource=resource)
        result = []
    except ValidationError as exc:
        result = exc.messages

    assert result == messages
