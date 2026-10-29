# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import signing

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _sign(url):
    return signing.Signer(salt="safe-redirect").sign(url)


def test_redirect_view_samesite_redirects(client):
    url = "https://example.com/target"
    response = client.get(
        "/redirect/",
        {"url": _sign(url)},
        headers={"referer": "http://testserver/origin/"},
    )

    assert response.status_code == 302
    assert response.url == url


def test_redirect_view_crosssite_shows_confirmation_with_escaped_hostname(client):
    url = "https://x<dialog open><h2>Session Expired</h2></dialog>y.com/"
    response = client.get("/redirect/", {"url": _sign(url)})

    assert response.status_code == 200
    content = response.content.decode()
    assert "<dialog open>" not in content
    assert "<h2>Session Expired</h2>" not in content
    assert "&lt;dialog open&gt;" in content

    response = client.get("/redirect/", {"url": _sign("https://example.com/target")})

    assert response.status_code == 200
    assert "example.com" in response.content.decode()

    response = client.get("/redirect/", {"url": _sign("/orga/event/")})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "params",
    (
        {"url": "tampered-value"},
        {},
        {"url": _sign("javascript:alert(document.domain)")},
        {"url": _sign("data:text/html,<script>alert(1)</script>")},
        {"url": _sign("vbscript:msgbox(1)")},
    ),
    ids=("bad_signature", "missing_url", "javascript", "data", "vbscript"),
)
def test_redirect_view_rejects_unsafe_targets(client, params):
    response = client.get("/redirect/", params)

    assert response.status_code == 400
