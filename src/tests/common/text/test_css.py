import pytest
from django.core.exceptions import ValidationError

from pretalx.common.text.css import validate_css, validate_key

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "css",
    (
        pytest.param(
            """
body {
  background-color: #000;
  display: none;
}
.some-descriptor {
  border-style: dotted dashed solid double;
  border-color: red green blue yellow;
  object-fit: cover;
}
#best-descriptor {
  border: 5px solid red;
}
""",
            id="standard_rules",
        ),
        pytest.param(
            """
@media print {
  .content {
    color: black;
    display: block;
  }
}
""",
            id="media_rules",
        ),
        pytest.param(
            """
div {
    background-color: #fff;
    background: transparent;
}
""",
            id="background_properties",
        ),
    ),
)
def test_validate_css_accepts_valid(css):
    assert validate_css(css) == css


@pytest.mark.parametrize(
    "css",
    (
        pytest.param(
            'a.link { content: url("https://malicious.site.com"); }',
            id="disallowed_property",
        ),
        pytest.param("this is not { valid css at all !!!}", id="malformed"),
        pytest.param(
            '@media screen { a { content: url("evil"); } }',
            id="invalid_nested_in_media",
        ),
    ),
)
def test_validate_css_rejects_invalid(css):
    with pytest.raises(ValidationError):
        validate_css(css)


@pytest.mark.parametrize(
    ("key", "style"),
    (
        ("color", {"color": "red"}),
        ("border-style", {"border-style": "solid dashed"}),
        ("margin-top", {"margin-top": "10px"}),
        ("padding-left", {"padding-left": "auto"}),
    ),
)
def test_validate_key_accepts_valid_property(key, style):
    validate_key(key=key, style=style)


@pytest.mark.parametrize(
    ("key", "style"),
    (
        ("border-image", {"border-image": "url(evil.png)"}),
        ("content", {"content": "'injected'"}),
    ),
)
def test_validate_key_rejects_invalid_property(key, style):
    with pytest.raises(ValidationError):
        validate_key(key=key, style=style)
