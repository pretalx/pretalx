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
