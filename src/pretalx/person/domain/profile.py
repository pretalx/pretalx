# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def apply_speaker_profile_changes(profile, changed_fields):
    """Run the side-effects keyed off the fields a caller just persisted on
    a speaker profile.
    """
    user = profile.user
    if not user:
        return
    if "name" in set(changed_fields) and profile.name and not user.name:
        user.name = profile.name
        user.save(update_fields=["name"])
