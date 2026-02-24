import pytest
from django import forms as django_forms
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.submission.forms.resource import ResourceForm

pytestmark = pytest.mark.unit


def test_resource_form_init_sets_description_required():
    form = ResourceForm()

    assert form.fields["description"].required is True
    assert form.fields["description"].widget.attrs.get("required") is True


def test_resource_form_valid_with_link_only():
    form = ResourceForm(
        data={
            "description": "Slides",
            "link": "https://example.com/slides.pdf",
            "is_public": True,
        }
    )

    assert form.is_valid(), form.errors


def test_resource_form_invalid_without_link_and_file():
    form = ResourceForm(
        data={"description": "Missing both", "link": "", "is_public": True}
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_resource_form_invalid_with_both_link_and_file():
    """Providing both a link and a file upload is not allowed."""
    form = ResourceForm(
        data={
            "description": "Both provided",
            "link": "https://example.com/slides.pdf",
            "is_public": True,
        },
        files={
            "resource": SimpleUploadedFile(
                "slides.pdf", b"fake-pdf-content", content_type="application/pdf"
            )
        },
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_resource_form_valid_with_file_only():
    form = ResourceForm(
        data={"description": "My slides", "link": "", "is_public": True},
        files={
            "resource": SimpleUploadedFile(
                "slides.pdf", b"fake-pdf-content", content_type="application/pdf"
            )
        },
    )

    assert form.is_valid(), form.errors


def test_resource_form_clean_skips_validation_on_delete():
    """When DELETE is set (formset deletion), clean() skips link/file validation.

    In formset context, Django adds a DELETE BooleanField. We simulate that here.
    """
    form = ResourceForm(
        data={"description": "", "link": "", "is_public": True, "DELETE": True}
    )
    form.fields["DELETE"] = django_forms.BooleanField(required=False)
    form.fields["description"].required = False

    assert form.is_valid(), form.errors
