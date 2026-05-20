# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import AttendeeProfileFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_attendee_profile_str():
    profile = AttendeeProfileFactory(user=UserFactory(name="Alice"))

    assert (
        str(profile)
        == f"AttendeeProfile(event={profile.event.slug}, user={profile.user})"
    )


def test_attendee_profile_log_parent_is_event():
    profile = AttendeeProfileFactory()

    assert profile.log_parent == profile.event
