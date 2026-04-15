# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import signing

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _sign(url):
    return signing.Signer(salt="safe-redirect").sign(url)


def test_redirect_view_samesite_redirects(client):
    """Same-site referer leads to an immediate redirect."""
    url = "https://example.com/target"
    response = client.get(
        "/redirect/",
        {"url": _sign(url)},
        headers={"referer": "http://testserver/origin/"},
    )

    assert response.status_code == 302
    assert response.url == url


def test_redirect_view_crosssite_shows_confirmation(client):
    """Cross-site (or missing) referer renders a confirmation page."""
    url = "https://example.com/target"
    response = client.get("/redirect/", {"url": _sign(url)})

    assert response.status_code == 200
    content = response.content.decode()
    assert "example.com" in content


def test_redirect_view_bad_signature_returns_400(client):
    response = client.get("/redirect/", {"url": "tampered-value"})

    assert response.status_code == 400


def test_redirect_view_missing_url_returns_400(client):
    response = client.get("/redirect/")

    assert response.status_code == 400


def test_redirect_view_escapes_hostname_html(client):
    """HTML in a crafted hostname must not render as real DOM elements."""
    url = "https://x<dialog open><h2>Session Expired</h2></dialog>y.com/"
    response = client.get("/redirect/", {"url": _sign(url)})

    assert response.status_code == 200
    content = response.content.decode()
    assert "<dialog open>" not in content
    assert "<h2>Session Expired</h2>" not in content
    assert "&lt;dialog open&gt;" in content
