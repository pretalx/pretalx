# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.domain.profile import apply_speaker_profile_changes
from tests.factories import SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_apply_speaker_profile_changes_email_calls_change_email():
    profile = SpeakerFactory(user=UserFactory(email="old@example.com"))

    apply_speaker_profile_changes(profile, ["email"], new_email="new@example.com")
    profile.user.refresh_from_db()

    assert profile.user.email == "new@example.com"


def test_apply_speaker_profile_changes_skips_email_not_in_changed_fields():
    profile = SpeakerFactory(user=UserFactory(email="old@example.com"))

    apply_speaker_profile_changes(profile, [], new_email="new@example.com")
    profile.user.refresh_from_db()

    assert profile.user.email == "old@example.com"


def test_apply_speaker_profile_changes_skips_email_when_unchanged_value():
    profile = SpeakerFactory(user=UserFactory(email="me@example.com"))

    apply_speaker_profile_changes(profile, ["email"], new_email="me@example.com")

    # No outbound mail (change_email would have queued one)
    assert profile.user.mails.count() == 0


def test_apply_speaker_profile_changes_syncs_name_to_empty_user():
    user = UserFactory(name="")
    profile = SpeakerFactory(user=user, name="Fresh Name")

    apply_speaker_profile_changes(profile, ["name"])
    user.refresh_from_db()

    assert user.name == "Fresh Name"


def test_apply_speaker_profile_changes_does_not_overwrite_existing_user_name():
    user = UserFactory(name="Existing Name")
    profile = SpeakerFactory(user=user, name="Profile Name")

    apply_speaker_profile_changes(profile, ["name"])
    user.refresh_from_db()

    assert user.name == "Existing Name"


def test_apply_speaker_profile_changes_skips_name_not_in_changed_fields():
    user = UserFactory(name="")
    profile = SpeakerFactory(user=user, name="Profile Name")

    apply_speaker_profile_changes(profile, [])
    user.refresh_from_db()

    assert user.name == ""
