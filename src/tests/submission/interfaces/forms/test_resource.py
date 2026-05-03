# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.submission.interfaces.forms import ResourceForm

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("data", "files", "expected_valid"),
    (
        (
            {"description": "Slides", "link": "https://example.com/slides.pdf"},
            None,
            True,
        ),
        (
            {"description": "Slides", "link": ""},
            {
                "resource": SimpleUploadedFile(
                    "slides.pdf", b"x", content_type="application/pdf"
                )
            },
            True,
        ),
        (
            {"description": "Both", "link": "https://example.com/slides.pdf"},
            {
                "resource": SimpleUploadedFile(
                    "slides.pdf", b"x", content_type="application/pdf"
                )
            },
            False,
        ),
        ({"description": "Neither", "link": ""}, None, False),
    ),
    ids=("link_only", "file_only", "both", "neither"),
)
def test_resource_form_link_xor_file(data, files, expected_valid):
    form = ResourceForm(data={**data, "is_public": True}, files=files)

    assert form.is_valid() is expected_valid, form.errors
    if not expected_valid:
        assert "__all__" in form.errors


def test_resource_form_skips_validation_when_marked_for_deletion():
    form = ResourceForm(
        data={"description": "d", "link": "", "is_public": True, "DELETE": "on"}
    )
    # Formset machinery injects this field on child forms; emulate it here so
    # we can exercise the form-only path without standing up an inline formset.
    form.fields["DELETE"] = forms.BooleanField(required=False)

    assert form.is_valid(), form.errors
