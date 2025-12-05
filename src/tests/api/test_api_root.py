# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json

import pytest
from django.conf import settings

from pretalx.api.versions import CURRENT_VERSION


@pytest.mark.django_db
def test_api_root_returns_metadata(client):
    response = client.get("/api/")
    content = json.loads(response.text)

    assert response.status_code == 200
    assert content["name"] == "pretalx"
    assert content["version"] == settings.PRETALX_VERSION
    assert content["api_version"] == CURRENT_VERSION
    assert content["urls"]["events"] == settings.SITE_URL + "/api/events/"
