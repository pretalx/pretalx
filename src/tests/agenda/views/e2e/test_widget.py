# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.django_db,
    pytest.mark.usefixtures("locmem_cache"),
]


def test_widget_data_cached_response_preserves_content_type(
    client, public_event_with_schedule
):
    """Cached widget responses must keep Content-Type: application/json.

    On the first (cold-cache) request, widget_data() returns a JsonResponse
    with the correct Content-Type. On the second request the response is
    served from cache via etag_cache_page(), which must preserve the
    Content-Type rather than falling back to the default text/html.

    Regression: etag_cache_page wraps the cached JsonResponse in a plain
    HttpResponse, discarding all headers including Content-Type. With
    text/html, HTML minification middleware can garble the JSON body.
    """
    event = public_event_with_schedule
    url = event.urls.schedule_widget_data

    cold_response = client.get(url)
    assert cold_response.status_code == 200
    assert cold_response["Content-Type"] == "application/json"
    cold_data = cold_response.json()

    hot_response = client.get(url)
    assert hot_response.status_code == 200
    assert hot_response["Content-Type"] == "application/json"
    hot_data = hot_response.json()

    assert hot_data == cold_data
