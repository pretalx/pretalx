# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.submission.models.resource import Resource, resource_path
from tests.factories import ResourceFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("filename", "expected_ext", "expected_stem"),
    (
        ("my-slides.pdf", ".pdf", "my-slides"),
        ("présentation.pptx", ".pptx", "presentation"),
    ),
    ids=["ascii", "unicode"],
)
def test_resource_path(filename, expected_ext, expected_stem):
    resource = ResourceFactory()
    slug = resource.submission.event.slug
    code = resource.submission.code

    result = resource_path(resource, filename)

    assert result.startswith(f"{slug}/submissions/{code}/resources/")
    assert result.endswith(expected_ext)
    assert expected_stem in result


def test_resource_queryset_active_needs_file_or_link():
    active_file = ResourceFactory(
        link=None, resource=SimpleUploadedFile("slides.pdf", b"content")
    )
    active_link = ResourceFactory(link="https://example.com/slides")
    ResourceFactory(link="", resource=None)

    assert set(Resource.objects.active()) == {active_file, active_link}


def test_resource_str():
    resource = ResourceFactory()

    assert (
        str(resource)
        == f"Resource(submission_id={resource.submission_id}, description={resource.description})"
    )


def test_resource_file_properties(settings):
    settings.SITE_URL = "https://pretalx.example.com"
    submission = SubmissionFactory()
    linked = ResourceFactory(submission=submission, link="https://example.com/slides")
    uploaded = ResourceFactory(
        submission=submission,
        link=None,
        resource=SimpleUploadedFile("slides.pdf", b"test content"),
    )
    missing = ResourceFactory(
        submission=submission,
        link=None,
        resource=SimpleUploadedFile("gone.pdf", b"test content"),
    )
    Path(missing.resource.path).unlink()
    empty = Resource.objects.select_related("submission__event").get(pk=linked.pk)
    empty.link = None
    empty.resource = None

    assert linked.url == "https://example.com/slides"
    assert uploaded.url.startswith("https://pretalx.example.com/")
    assert uploaded.url.endswith(".pdf")
    assert empty.url is None
    assert uploaded.filename.startswith("slides")
    assert uploaded.filename.endswith(".pdf")
    assert empty.filename is None
    assert uploaded.size == len(b"test content")
    assert missing.size is None
    assert empty.size is None


def test_resource_delete_removes_file(django_capture_on_commit_callbacks):
    f = SimpleUploadedFile("test_resource.txt", b"test content")
    resource = ResourceFactory(link=None, resource=f)
    linked = ResourceFactory(submission=resource.submission, link="https://example.com")
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)

    with django_capture_on_commit_callbacks(execute=True):
        resource.delete()
        linked.delete()

    assert not resource.resource.storage.exists(file_path)
    assert not Resource.objects.filter(submission=resource.submission).exists()


def test_resource_as_markdown():
    submission = SubmissionFactory()
    resources = [
        ResourceFactory(
            submission=submission, link="https://example.com", description="Slides"
        ),
        ResourceFactory(
            submission=submission, link="https://example.com/2", description=""
        ),
        ResourceFactory(submission=submission, link="", description="My Slides"),
        ResourceFactory(
            submission=submission,
            resource=SimpleUploadedFile("slides.pdf", b"content"),
            description="",
            link=None,
        ),
        ResourceFactory(
            submission=submission, resource=None, description="", link=None
        ),
    ]

    lines = [resource.as_markdown for resource in resources]

    assert lines[:3] == [
        "[Slides](https://example.com)",
        "https://example.com/2",
        "File: My Slides",
    ]
    assert lines[3].startswith("File: slides_")
    assert lines[3].endswith(".pdf")
    assert lines[4] is None
