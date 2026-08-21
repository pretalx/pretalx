# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope, scopes_disabled

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("item_count", (1, 3))
def test_featured_view_shows_featured_talks(
    client, item_count, django_assert_num_queries
):
    event = EventFactory(feature_flags={"show_featured": "always", "use_tracks": True})
    with scopes_disabled():
        track = TrackFactory(event=event)
        featured = SubmissionFactory.create_batch(
            item_count,
            event=event,
            is_featured=True,
            state=SubmissionStates.CONFIRMED,
            track=track,
        )
        speakers = []
        for submission in featured:
            submission_speakers = SpeakerFactory.create_batch(2, event=event)
            submission.speakers.add(*submission_speakers)
            speakers += submission_speakers
        not_featured = SubmissionFactory(
            event=event, is_featured=False, state=SubmissionStates.CONFIRMED
        )

    with django_assert_num_queries(5):
        response = client.get(event.urls.featured, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in featured)
    assert all(speaker.get_display_name() in content for speaker in speakers)
    assert not_featured.title not in content


def test_featured_view_redirects_to_schedule_when_released(client):
    event = EventFactory(feature_flags={"show_featured": "pre_schedule"})
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")

    response = client.get(event.urls.featured)

    assert response.status_code == 302
    assert response.url == event.urls.schedule


def test_featured_view_visible_when_schedule_hidden(client):
    event = EventFactory(
        feature_flags={"show_featured": "always", "show_schedule": False}
    )
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")
        featured = SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )

    response = client.get(event.urls.featured, follow=True)

    assert response.status_code == 200
    assert featured.title in response.content.decode()


def test_featured_view_uses_custom_text(client):
    event = EventFactory(
        feature_flags={"show_featured": "always"},
        featured_sessions_text="Have a look at **these**.",
    )
    with scopes_disabled():
        SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )

    content = client.get(event.urls.featured, follow=True).content.decode()

    assert "Have a look at <strong>these</strong>." in content
    assert "Welcome to our list of featured sessions!" not in content


def test_sneakpeek_redirect_to_featured(client, event):
    url = str(event.urls.featured).replace("featured", "sneak")

    response = client.get(url)

    assert response.status_code == 301
    assert response.url == event.urls.featured
