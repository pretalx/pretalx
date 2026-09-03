# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.test import override_settings

from tests.factories import UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def rest_framework(**rates):
    return {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}


@override_settings(REST_FRAMEWORK=rest_framework(user="1/minute"))
def test_request_over_the_limit_is_rejected(client, public_event_with_schedule):
    client.force_login(UserFactory())
    url = f"/api/events/{public_event_with_schedule.slug}/submissions/favourites/"

    first = client.get(url, follow=True)
    second = client.get(url, follow=True)

    assert first.status_code == 200
    assert first.json() == []
    assert second.status_code == 429
    assert second.json()["detail"].startswith("Request was throttled.")
    assert int(second.headers["Retry-After"]) <= 60


@override_settings(REST_FRAMEWORK=rest_framework(user="1/minute"))
def test_anonymous_requests_are_not_throttled(client):
    responses = [client.get("/api/events/") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]
