# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_event_css_no_color(event, client):
    response = client.get(
        reverse("agenda:event.css", kwargs={"event": event.slug}),
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    assert b"--color-primary" not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("color", "expect_dark_text_override"),
    (
        # Dark colors - no override needed, white text is fine
        ("#000000", False),
        ("#0000ff", False),
        ("#800000", False),  # Maroon
        # Medium/light colors - need dark text override
        ("#3aa57c", False),  # pretalx green
        ("#ffffff", True),
        ("#ffff00", True),
        ("#00ffff", True),
    ),
)
def test_event_css_with_color(event, client, color, expect_dark_text_override):
    event.primary_color = color
    event.save()

    response = client.get(
        reverse("agenda:event.css", kwargs={"event": event.slug}),
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    content = response.content.decode()
    assert f"--color-primary: {color}" in content
    if expect_dark_text_override:
        assert "--color-text-on-primary: var(--color-text)" in content
    else:
        assert "--color-text-on-primary" not in content


@pytest.mark.django_db
def test_event_css_orga_target(event, client):
    event.primary_color = "#ffff00"  # Yellow - would normally need dark text
    event.save()

    response = client.get(
        reverse("agenda:event.css", kwargs={"event": event.slug}),
        {"target": "orga"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "--color-primary-event: #ffff00" in content
    assert "--color-text-on-primary-event" in content


@pytest.mark.django_db
def test_event_css_etag_includes_dark_text_state(event, client):
    event.primary_color = "#000000"  # Dark - no dark text needed
    event.save()

    response1 = client.get(
        reverse("agenda:event.css", kwargs={"event": event.slug}),
    )
    etag1 = response1.get("ETag")

    event.primary_color = "#ffffff"
    event.save()

    response2 = client.get(
        reverse("agenda:event.css", kwargs={"event": event.slug}),
    )
    etag2 = response2.get("ETag")

    assert etag1 != etag2
