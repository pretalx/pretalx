import pytest

from pretalx.api.documentation import (
    build_expand_docs,
    build_search_docs,
    postprocess_schema,
)
from pretalx.mail.models import MailTemplateRoles

pytestmark = pytest.mark.unit


def test_build_search_docs_without_extra_description():
    result = build_search_docs("title", "abstract")

    assert result.name == "q"
    assert '"title"' in result.description
    assert '"abstract"' in result.description
    assert result.description == 'A search term, searching in `"title"`,`"abstract"`.'


def test_build_expand_docs_returns_parameter_with_enum():
    result = build_expand_docs("submissions", "speakers")

    assert result.name == "expand"
    assert result.enum == ("submissions", "speakers")
    assert result.many is True


def test_build_search_docs_with_extra_description():
    result = build_search_docs("title", extra_description="Case-insensitive.")

    assert "Case-insensitive." in result.description
    assert '"title"' in result.description


def _make_schema_skeleton():
    """Build a minimal schema dict that postprocess_schema can operate on."""
    return {
        "paths": {
            "/api/": {"get": {"security": [{"token": []}]}},
            "/api/events/": {"get": {"security": [{"token": []}]}},
            "/api/events/{event}/": {"get": {"security": [{"token": []}]}},
        },
        "components": {"schemas": {"MailTemplate": {"properties": {}}}},
        "tags": [],
    }


def test_postprocess_schema_removes_security_from_public_endpoints():
    schema = _make_schema_skeleton()

    result = postprocess_schema(schema, generator=None, request=None, public=True)

    assert "security" not in result["paths"]["/api/"]["get"]
    assert "security" not in result["paths"]["/api/events/"]["get"]
    assert "security" not in result["paths"]["/api/events/{event}/"]["get"]


def test_postprocess_schema_adds_role_enum():
    schema = _make_schema_skeleton()

    result = postprocess_schema(schema, generator=None, request=None, public=True)

    role_enum = result["components"]["schemas"]["RoleEnum"]
    assert role_enum["type"] == "string"
    expected_keys = list(dict(MailTemplateRoles.choices).keys())
    assert role_enum["enum"] == expected_keys


def test_postprocess_schema_patches_mail_template_role_property():
    schema = _make_schema_skeleton()

    result = postprocess_schema(schema, generator=None, request=None, public=True)

    role_prop = result["components"]["schemas"]["MailTemplate"]["properties"]["role"]
    assert role_prop["nullable"] is True
    assert role_prop["$ref"] == "#/components/schemas/RoleEnum"
