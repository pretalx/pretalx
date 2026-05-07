# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.person.domain.user import change_email


def apply_speaker_profile_changes(profile, changed_fields, *, new_email=None):
    """Run the side-effects keyed off the fields a caller just persisted on
    a speaker profile.
    """
    fields = set(changed_fields)
    user = profile.user
    if "email" in fields and new_email and new_email != user.email:
        change_email(user, new_email)
    if "name" in fields and profile.name and not user.name:
        user.name = profile.name
        user.save(update_fields=["name"])
