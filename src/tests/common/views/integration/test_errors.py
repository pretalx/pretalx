# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.test import Client

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize(
    "host",
    ("1.2.3.4:80:80", "foo_bar.example.com", "", "exa mple.com"),
    ids=("double_port", "underscore", "empty", "space"),
)
def test_malformed_host_header_renders_400_page(client, host):
    # CommonMiddleware raises DisallowedHost before AuthenticationMiddleware runs,
    # so the 400 page has to render without request.user.
    response = client.get("/some/scanned/path", HTTP_HOST=host)

    assert response.status_code == 400
    assert "Bad request." in response.content.decode()


@pytest.mark.django_db
def test_unrouted_api_path_returns_json_404(client):
    response = client.get("/api/no-such-endpoint/")

    assert response.status_code == 404
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.json() == {"detail": "Not found."}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    ("/no-such-page/", "/apinotreally/"),
    ids=("plain", "api_prefix_without_slash"),
)
def test_unrouted_non_api_path_still_returns_html_404(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert "Page not found" in response.content.decode()


@pytest.mark.django_db
def test_malformed_api_query_string_returns_json_400(client):
    response = client.get("/api/events/?q=%00")

    assert response.status_code == 400
    assert response.headers["Content-Type"] == "application/json"
    assert response.json() == {"detail": "Malformed request."}


@pytest.mark.django_db
def test_csrf_failure_on_api_path_returns_json_403(event):
    csrf_client = Client(enforce_csrf_checks=True)

    response = csrf_client.post(f"/api/events/{event.slug}/talks/1")

    assert response.status_code == 403
    assert response.headers["Content-Type"] == "application/json"
    assert response.json()["detail"].startswith("CSRF Failed: ")
