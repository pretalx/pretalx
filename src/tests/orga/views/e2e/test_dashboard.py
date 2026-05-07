# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import SpeakerFactory, SubmissionFactory, TalkSlotFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def test_dashboard_speaker_tile_links_to_filtered_speaker_list(client, event):
    """The dashboard speaker tile counts confirmed speakers and links to a
    pre-filtered speaker list — that list must show speakers (accepted
    submissions) and exclude submitters (no accepted submissions)."""
    with scopes_disabled():
        accepted_speaker = SpeakerFactory(event=event, name="Accepted Speaker")
        accepted_submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED
        )
        accepted_submission.speakers.add(accepted_speaker)
        slot = TalkSlotFactory(submission=accepted_submission, is_visible=True)
        freeze_schedule(slot.schedule, "v1", notify_speakers=False)

        rejected_submitter = SpeakerFactory(event=event, name="Rejected Submitter")
        rejected_submission = SubmissionFactory(
            event=event, state=SubmissionStates.REJECTED
        )
        rejected_submission.speakers.add(rejected_submitter)

    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)
    assert response.status_code == 200
    speaker_tiles = [
        t
        for t in response.context["tiles"]
        if "speaker" in str(t.get("small", "")).lower()
    ]
    assert len(speaker_tiles) == 1
    tile = speaker_tiles[0]
    assert tile["large"] == 1

    response = client.get(tile["url"])

    assert response.status_code == 200
    content = response.content.decode()
    assert accepted_speaker.get_display_name() in content
    assert rejected_submitter.get_display_name() not in content
