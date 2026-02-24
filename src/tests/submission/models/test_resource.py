import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled

from pretalx.submission.models.resource import Resource, resource_path
from tests.factories import ResourceFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("filename", "expected_ext", "expected_stem"),
    (
        ("my-slides.pdf", ".pdf", "my-slides"),
        ("présentation.pptx", ".pptx", "presentation"),
    ),
    ids=["ascii", "unicode"],
)
@pytest.mark.django_db
def test_resource_path(filename, expected_ext, expected_stem):
    resource = ResourceFactory()
    slug = resource.submission.event.slug
    code = resource.submission.code

    result = resource_path(resource, filename)

    assert result.startswith(f"{slug}/submissions/{code}/resources/")
    assert result.endswith(expected_ext)
    assert expected_stem in result


@pytest.mark.django_db
def test_resource_str():
    resource = ResourceFactory()

    assert (
        str(resource)
        == f"Resource(event={resource.submission.event.slug}, submission={resource.submission.title})"
    )


@pytest.mark.django_db
def test_resource_url_returns_link_when_set():
    resource = ResourceFactory(link="https://example.com/slides")

    assert resource.url == "https://example.com/slides"


@pytest.mark.django_db
def test_resource_url_returns_file_url_when_no_link(settings):
    """When resource has a file but no link, url returns base_url + file url."""
    settings.SITE_URL = "https://pretalx.example.com"
    f = SimpleUploadedFile("file.pdf", b"test content")
    resource = ResourceFactory(link=None, resource=f)

    result = resource.url

    assert result.startswith("https://pretalx.example.com/")
    assert result.endswith(".pdf")


@pytest.mark.django_db
def test_resource_url_returns_none_when_no_link_no_file():
    resource = ResourceFactory(link=None)

    with scopes_disabled():
        resource = Resource.objects.get(pk=resource.pk)
    resource.resource = None

    assert resource.url is None


@pytest.mark.django_db
def test_resource_filename_returns_name_for_file():
    f = SimpleUploadedFile("slides.pdf", b"content")
    resource = ResourceFactory(link=None, resource=f)

    assert resource.filename.endswith(".pdf")
    assert "slides" in resource.filename


@pytest.mark.django_db
def test_resource_filename_returns_none_when_no_file():
    resource = ResourceFactory(link="https://example.com")

    with scopes_disabled():
        resource = Resource.objects.get(pk=resource.pk)
    resource.resource = None

    assert resource.filename is None


@pytest.mark.django_db
def test_resource_delete_removes_file():
    f = SimpleUploadedFile("test_resource.txt", b"test content")
    resource = ResourceFactory(link=None, resource=f)
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)

    with scopes_disabled():
        resource.delete()

    assert not resource.resource.storage.exists(file_path)


@pytest.mark.django_db
def test_resource_delete_without_file():
    """Deleting a link-only resource doesn't raise."""
    resource = ResourceFactory(link="https://example.com")

    with scopes_disabled():
        pk = resource.pk
        resource.delete()

    with scopes_disabled():
        assert not Resource.objects.filter(pk=pk).exists()
