# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.domain.picture import assign_avatar, set_avatar
from pretalx.person.models import SpeakerProfile, User
from tests.factories import ProfilePictureFactory, SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_set_avatar_creates_picture_assigns_it_and_bumps_the_old_one(make_image, event):
    user = UserFactory()
    old_pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = old_pic
    speaker.save(update_fields=["profile_picture"])
    old_updated = old_pic.updated

    new_pic = set_avatar(speaker, make_image("new.png"))

    assert new_pic is not None
    assert speaker.profile_picture == new_pic
    speaker.refresh_from_db(fields=["profile_picture"])
    assert speaker.profile_picture_id == new_pic.pk
    user.refresh_from_db()
    assert user.profile_picture == new_pic
    old_pic.refresh_from_db()
    assert old_pic.updated >= old_updated


def test_set_avatar_managed_profile_creates_ownerless_picture(make_image, event):
    speaker = SpeakerFactory(event=event, user=None)

    new_pic = set_avatar(speaker, make_image())

    speaker.refresh_from_db()
    assert speaker.profile_picture_id == new_pic.pk
    assert new_pic.user is None


def test_set_avatar_does_not_override_user_picture(make_image, event):
    user = UserFactory()
    existing_pic = ProfilePictureFactory(user=user, avatar=make_image())
    user.profile_picture = existing_pic
    user.save(update_fields=["profile_picture"])
    speaker = SpeakerFactory(event=event, user=user)
    speaker.user = User.objects.get(pk=user.pk)

    set_avatar(speaker, make_image("new.png"))

    user.refresh_from_db()
    assert user.profile_picture == existing_pic


def test_set_avatar_on_user_directly(make_image):
    user = UserFactory()

    new_pic = set_avatar(user, make_image())

    user.refresh_from_db()
    assert user.profile_picture == new_pic


def test_assign_avatar_assigns_keeps_and_clears_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)

    assign_avatar(speaker, user, pic)

    assert speaker.profile_picture_id == pic.pk
    assert SpeakerProfile.objects.get(pk=speaker.pk).profile_picture_id == pic.pk
    user.refresh_from_db()
    assert user.profile_picture == pic
    pic.refresh_from_db()
    timestamp = pic.updated

    assign_avatar(speaker, user, pic)

    pic.refresh_from_db()
    assert pic.updated == timestamp

    assign_avatar(speaker, user, None)

    assert speaker.profile_picture_id is None
    assert SpeakerProfile.objects.get(pk=speaker.pk).profile_picture_id is None
    pic.refresh_from_db()
    assert pic.updated > timestamp


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
    assert speaker.profile_picture_id == new_pic.pk
