# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

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
    response = client.get(
        "/some/scanned/path", HTTP_HOST=host, raise_request_exception=False
    )

    assert response.status_code == 400
    assert "Bad request." in response.content.decode()
