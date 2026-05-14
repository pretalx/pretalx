# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.person.models import ProfilePicture


def assign_avatar(instance, user, new_picture):
    """Assign ``new_picture`` to ``instance.profile_picture`` (``None`` clears).

    Bumps the replaced picture's timestamp for cleanup, and seeds the
    user-level avatar from a speaker's first picture.
    """
    old_picture = instance.profile_picture
    if new_picture == old_picture:
        return
    instance.profile_picture = new_picture
    instance.save(update_fields=["profile_picture"])
    if old_picture:
        old_picture.save(update_fields=["updated"])
    if new_picture and user and not user.profile_picture:
        user.profile_picture = new_picture
        user.save(update_fields=["profile_picture"])


def set_avatar(instance, file):
    """Create a fresh ``ProfilePicture`` from ``file`` and assign it to
    ``instance`` (a ``User`` or ``SpeakerProfile``)."""
    user = getattr(instance, "user", None)
    new_picture = ProfilePicture.objects.create(user=user or instance, avatar=file)
    new_picture.process_image("avatar", generate_thumbnail=True)
    assign_avatar(instance, user, new_picture)
    return new_picture
