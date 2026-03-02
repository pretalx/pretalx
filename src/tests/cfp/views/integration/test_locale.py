# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.urls import reverse

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_locale_set_redirects_and_sets_cookie(client, event):
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=de")

    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"


def test_locale_set_with_next_param(client, event):
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=en&next=/{event.slug}/cfp")

    assert response.status_code == 302
    assert f"/{event.slug}/cfp" in response.url


def test_locale_set_global_endpoint(client):
    """The global locale/set endpoint (outside event context) also works."""
    response = client.get("/locale/set?locale=de")

    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"
