# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import SpeakerRoleFactory, TeamFactory, TrackFactory, UserFactory


@pytest.fixture
def review_user(event):
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
    return SpeakerRoleFactory(submission__event=event, speaker__event=event).submission


@pytest.fixture
def other_submission(event):
    return SpeakerRoleFactory(submission__event=event, speaker__event=event).submission


@pytest.fixture
def track(event):
    event.feature_flags["use_tracks"] = True
    event.save()
    return TrackFactory(event=event)
