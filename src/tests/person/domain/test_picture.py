# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.domain.picture import assign_avatar, set_avatar
from tests.factories import ProfilePictureFactory, SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_set_avatar_creates_picture_and_assigns_to_user(make_image, event):
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)

    new_pic = set_avatar(speaker, make_image())

    assert new_pic is not None
    speaker.refresh_from_db()
    assert speaker.profile_picture == new_pic
    user.refresh_from_db()
    assert user.profile_picture == new_pic


def test_set_avatar_bumps_old_picture(make_image, event):
    """When replacing an avatar, the old picture gets its updated field bumped."""
    user = UserFactory()
    old_pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = old_pic
    speaker.save(update_fields=["profile_picture"])
    old_updated = old_pic.updated

    new_pic = set_avatar(speaker, make_image("new.png"))

    old_pic.refresh_from_db()
    assert old_pic.updated >= old_updated
    assert speaker.profile_picture == new_pic


def test_set_avatar_does_not_override_user_picture(make_image, event):
    """When user already has a profile_picture, set_avatar doesn't override it."""
    user = UserFactory()
    existing_pic = ProfilePictureFactory(user=user, avatar=make_image())
    user.profile_picture = existing_pic
    user.save(update_fields=["profile_picture"])
    speaker = SpeakerFactory(event=event, user=user)

    set_avatar(speaker, make_image("new.png"))

    user.refresh_from_db()
    assert user.profile_picture == existing_pic


def test_set_avatar_on_user_directly(make_image):
    """Calling set_avatar on a User assigns the picture to the user itself."""
    user = UserFactory()

    new_pic = set_avatar(user, make_image())

    user.refresh_from_db()
    assert user.profile_picture == new_pic


def test_assign_avatar_assigns_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)

    assign_avatar(speaker, user, pic)

    speaker.refresh_from_db()
    assert speaker.profile_picture == pic
    user.refresh_from_db()
    assert user.profile_picture == pic


def test_assign_avatar_clears_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    pic.refresh_from_db()
    old_updated = pic.updated

    assign_avatar(speaker, user, None)

    speaker.refresh_from_db()
    assert speaker.profile_picture is None
    pic.refresh_from_db()
    assert pic.updated > old_updated


def test_assign_avatar_noop_when_unchanged(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    pic.refresh_from_db()
    timestamp = pic.updated

    assign_avatar(speaker, user, pic)

    pic.refresh_from_db()
    assert pic.updated == timestamp


def test_assign_avatar_does_not_override_user_picture(make_image, event):
    user = UserFactory()
    existing_pic = ProfilePictureFactory(user=user, avatar=make_image())
    user.profile_picture = existing_pic
    user.save(update_fields=["profile_picture"])
    speaker = SpeakerFactory(event=event, user=user)
    new_pic = ProfilePictureFactory(user=user, avatar=make_image("new.png"))

    assign_avatar(speaker, user, new_pic)

    user.refresh_from_db()
    assert user.profile_picture == existing_pic
    speaker.refresh_from_db()
    assert speaker.profile_picture == new_pic
