# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)


@pytest.fixture
def review_user(event):
    """User with reviewer-only access to the event."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_submissions=False,
        is_reviewer=True,
    )
    team.members.add(user)
    return user


@pytest.fixture
def submission(event):
    """A submitted submission with one speaker on the test event."""
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    return sub


@pytest.fixture
def other_submission(event):
    """A second submission on the same event with a different speaker."""
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    return sub


@pytest.fixture
def track(event):
    """A track on the test event (enables use_tracks feature flag)."""
    event.feature_flags["use_tracks"] = True
    event.save()
    return TrackFactory(event=event)
