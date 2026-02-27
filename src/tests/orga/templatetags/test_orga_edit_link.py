import pytest

from pretalx.orga.templatetags.orga_edit_link import orga_edit_link

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("url", "target", "expected_href"),
    (
        ("https://foo.bar", None, "https://foo.bar"),
        ("https://foo.bar", "", "https://foo.bar"),
        ("https://foo.bar", "target", "https://foo.bar#target"),
    ),
)
def test_orga_edit_link_href(url, target, expected_href):
    result = orga_edit_link(url, target)
    assert f'href="{expected_href}"' in result


def test_orga_edit_link_contains_edit_classes():
    result = orga_edit_link("https://example.com")
    assert 'class="btn btn-xs btn-outline-info orga-edit-link ml-auto"' in result
    assert "fa-pencil" in result


def test_orga_edit_link_returns_safe_string():
    """The return value is marked safe so Django won't auto-escape it."""
    result = orga_edit_link("https://example.com")
    assert hasattr(result, "__html__")
