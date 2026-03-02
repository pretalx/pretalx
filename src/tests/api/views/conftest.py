# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import SpeakerRoleFactory, TeamFactory, TrackFactory, UserFactory


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
    return SpeakerRoleFactory(submission__event=event, speaker__event=event).submission


@pytest.fixture
def other_submission(event):
    """A second submission on the same event with a different speaker."""
    return SpeakerRoleFactory(submission__event=event, speaker__event=event).submission


@pytest.fixture
def track(event):
    """A track on the test event (enables use_tracks feature flag)."""
    event.feature_flags["use_tracks"] = True
    event.save()
    return TrackFactory(event=event)
