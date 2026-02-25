import pytest
from rest_framework.exceptions import APIException

from pretalx.api.versions import (
    CURRENT_VERSION,
    SERIALIZER_REGISTRY,
    SUPPORTED_VERSIONS,
    get_api_version_from_request,
    get_serializer_by_version,
    register_serializer,
)
from tests.factories import UserApiTokenFactory
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


def test_register_serializer_with_string_version():
    """When versions is a string, it is wrapped in a list."""

    @register_serializer(versions="v1", class_name="_TestStringVersion")
    class _TestSerializer:
        pass

    assert SERIALIZER_REGISTRY["_TestStringVersion", "v1"] is _TestSerializer


def test_register_serializer_with_default_versions():
    """When versions is None, all SUPPORTED_VERSIONS are registered."""

    @register_serializer(class_name="_TestDefaultVersions")
    class _TestSerializer:
        pass

    for version in SUPPORTED_VERSIONS:
        assert SERIALIZER_REGISTRY["_TestDefaultVersions", version] is _TestSerializer


def test_register_serializer_uses_class_name_by_default():
    @register_serializer(versions=["v1"])
    class _TestAutoName:
        pass

    assert SERIALIZER_REGISTRY["_TestAutoName", "v1"] is _TestAutoName


def test_get_serializer_by_version_returns_registered_class():
    @register_serializer(versions=["v1"], class_name="_TestLookup")
    class _TestSerializer:
        pass

    result = get_serializer_by_version("_TestLookup", "v1")

    assert result is _TestSerializer


def test_get_serializer_by_version_raises_for_missing():
    with pytest.raises(KeyError):
        get_serializer_by_version("_NonExistent", "v1")


@pytest.mark.django_db
def test_get_api_version_from_request_uses_header():
    """The pretalx-version header takes precedence."""
    request = make_api_request()
    request._request.META["HTTP_PRETALX_VERSION"] = CURRENT_VERSION

    result = get_api_version_from_request(request)

    assert result == CURRENT_VERSION


@pytest.mark.django_db
def test_get_api_version_from_request_uses_token_version():
    """When no header is present, the token's version is used."""
    token = UserApiTokenFactory(version="v1")
    request = make_api_request(auth=token)

    result = get_api_version_from_request(request)

    assert result == "v1"


@pytest.mark.django_db
def test_get_api_version_from_request_defaults_to_current():
    """When neither header nor token version is set, CURRENT_VERSION is used."""
    request = make_api_request()

    result = get_api_version_from_request(request)

    assert result == CURRENT_VERSION


@pytest.mark.django_db
def test_get_api_version_from_request_rejects_unsupported_version():
    request = make_api_request()
    request._request.META["HTTP_PRETALX_VERSION"] = "v-nonexistent"

    with pytest.raises(APIException, match="Unsupported version"):
        get_api_version_from_request(request)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("initial_version", "expected_version"),
    ((None, CURRENT_VERSION), ("LEGACY", "LEGACY")),
    ids=["saves_on_empty", "preserves_existing"],
)
def test_get_api_version_from_request_token_version_persistence(
    initial_version, expected_version
):
    """When a token has no version, the resolved version is saved; an existing
    version is never overwritten."""
    token = UserApiTokenFactory(version=initial_version)
    request = make_api_request(auth=token)

    result = get_api_version_from_request(request)
    token.refresh_from_db()

    assert result == expected_version
    assert token.version == expected_version
