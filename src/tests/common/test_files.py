# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.files import (
    DOCUMENT_UPLOAD_TYPES,
    FILE_TYPE_GROUPS,
    is_image_only,
    resolve_file_types,
)

pytestmark = pytest.mark.unit


def test_file_type_groups_partition_document_upload_types():
    members = [ct for group in FILE_TYPE_GROUPS.values() for ct in group]

    assert sorted(members) == sorted(DOCUMENT_UPLOAD_TYPES)


IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"]


@pytest.mark.parametrize(
    ("tokens", "expected"),
    (
        (None, list(DOCUMENT_UPLOAD_TYPES)),
        ([], list(DOCUMENT_UPLOAD_TYPES)),
        (
            ["presentation/*"],
            [
                "application/vnd.ms-powerpoint",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.oasis.opendocument.presentation",
            ],
        ),
        (["image/*", "application/pdf"], [*IMAGE_TYPES, "application/pdf"]),
        (["image/png", "image/*"], IMAGE_TYPES),
    ),
    ids=("none", "empty", "wildcard", "wildcard_and_specific", "redundant_specific"),
)
def test_resolve_file_types(tokens, expected):
    assert resolve_file_types(tokens) == {
        content_type: DOCUMENT_UPLOAD_TYPES[content_type] for content_type in expected
    }


def test_resolve_file_types_rejects_unknown_token():
    with pytest.raises(KeyError):
        resolve_file_types(["image/png", "application/x-msdownload"])


@pytest.mark.parametrize(
    ("tokens", "expected"),
    ((["image/*"], True), (["image/png", "image/webp"], True), ([], False)),
)
def test_is_image_only(tokens, expected):
    assert is_image_only(resolve_file_types(tokens)) is expected
