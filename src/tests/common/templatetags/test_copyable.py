import pytest

from pretalx.common.templatetags.copyable import copyable

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ('"foo', '"foo'),
        (
            "foo",
            """
    <span data-destination="foo"
            class="copyable-text"
            data-toggle="tooltip"
            data-placement="top"
            title="Copy"
            data-success-message="Copied!"
            data-error-message="Failed to copy"
            role="button"
            tabindex="0"
    >
        foo
    </span>""",
        ),
    ),
)
def test_copyable(value, expected):
    assert copyable(value) == expected
