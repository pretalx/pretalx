import pytest
from django.conf import settings

from pretalx.api.versions import CURRENT_VERSION

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_root_returns_api_metadata(client):
    """GET /api/ returns pretalx name, version, api_version, and events URL."""
    response = client.get("/api/")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "name": "pretalx",
        "version": settings.PRETALX_VERSION,
        "api_version": CURRENT_VERSION,
        "urls": {"events": settings.SITE_URL + "/api/events/"},
    }
