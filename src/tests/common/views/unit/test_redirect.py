import urllib.parse

import pytest
from django.core import signing

from pretalx.common.views.redirect import _is_samesite_referer, safelink
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("referer", "expected"),
    (
        ("http://testserver/some/page/", True),
        (None, False),
        ("http://evil.example.com/page/", False),
        ("//testserver/page/", False),
        ("https://testserver/page/", False),
    ),
    ids=[
        "same_origin",
        "no_header",
        "different_host",
        "empty_scheme",
        "different_scheme",
    ],
)
def test_is_samesite_referer(event, referer, expected):
    kwargs = {"headers": {"referer": referer}} if referer is not None else {}
    request = make_request(event, **kwargs)

    assert _is_samesite_referer(request) is expected


def test_safelink_produces_signed_url():
    url = "https://example.com"

    result = safelink(url)

    assert result.startswith("/redirect/?url=")
    signer = signing.Signer(salt="safe-redirect")
    encoded_signed = result.split("?url=")[1]
    signed = urllib.parse.unquote(encoded_signed)
    assert signer.unsign(signed) == url
