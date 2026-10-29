# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings

from pretalx.event.models import Event
from pretalx.person.models import SpeakerProfile, User
from pretalx.person.models.picture import ProfilePicture, picture_path
from tests.factories import ProfilePictureFactory, SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("kwargs", "expected_name"),
    (
        ({"user": User(code="ABCDEF")}, "ABCDEF"),
        ({"user": User(code=None)}, "avatar"),
        ({"user": None}, "avatar"),
        ({}, "avatar"),
    ),
    ids=["with_code", "without_code", "user_cached_as_none", "user_not_loaded"],
)
def test_picture_path(kwargs, expected_name):
    path = picture_path(ProfilePicture(**kwargs), "photo.jpg")

    assert path.startswith(f"avatars/{expected_name}_")
    assert path.endswith(".jpg")


def test_profile_picture_stored_without_user(make_image):
    pic = ProfilePictureFactory(user=None, avatar=make_image())

    pic = ProfilePicture.objects.get(pk=pic.pk)
    assert pic.user is None
    assert pic.avatar.name.startswith("avatars/avatar_")


def test_profile_picture_avatar_accessors(make_image):
    user = UserFactory()
    without = ProfilePictureFactory(user=user)
    with_avatar = ProfilePictureFactory(user=user, avatar=make_image())
    falsy_string = ProfilePicture(user=user)
    falsy_string.avatar = "False"

    assert without.has_avatar is False
    assert without.avatar_url is None
    assert without.get_avatar_url() == ""
    assert falsy_string.has_avatar is False
    assert with_avatar.has_avatar is True
    assert with_avatar.avatar_url == with_avatar.avatar.url
    assert with_avatar.get_avatar_url().startswith(settings.SITE_URL)


@pytest.mark.parametrize(
    ("custom_domain", "expected_prefix"),
    (("https://custom.example.com", "https://custom.example.com"), (None, None)),
    ids=["with_custom_domain", "without_custom_domain"],
)
def test_profile_picture_get_avatar_url_event_domain(
    make_image, event, custom_domain, expected_prefix
):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    event.custom_domain = custom_domain
    url = pic.get_avatar_url(event=event)
    assert url.startswith(expected_prefix or settings.SITE_URL)


@pytest.mark.parametrize("thumbnail", ("tiny", "default"))
def test_profile_picture_get_avatar_url_thumbnail_fallback(
    make_image, thumbnail, monkeypatch
):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    calls = []
    monkeypatch.setattr(
        "pretalx.common.image.queue_thumbnail_regeneration", calls.append
    )

    result = pic.get_avatar_url(thumbnail=thumbnail)

    assert result == f"{settings.SITE_URL}{pic.avatar.url}"
    assert calls == [pic.avatar]


@pytest.mark.parametrize(
    ("thumbnail", "field_name", "file_name"),
    (
        ("tiny", "avatar_thumbnail_tiny", "tiny.png"),
        ("default", "avatar_thumbnail", "thumb.png"),
    ),
)
def test_profile_picture_get_avatar_url_thumbnail_exists(
    make_image, thumbnail, field_name, file_name
):
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=make_image(), **{field_name: make_image(file_name)}
    )
    url = pic.get_avatar_url(thumbnail=thumbnail)
    assert url.startswith(settings.SITE_URL)


def test_profile_picture_get_avatar_url_unknown_thumbnail_size(make_image, monkeypatch):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    calls = []
    monkeypatch.setattr(
        "pretalx.common.image.queue_thumbnail_regeneration", calls.append
    )

    result = pic.get_avatar_url(thumbnail="nonexistent_size")

    assert result is None
    assert calls == []


def test_profile_picture_mixin_with_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    speaker = SpeakerProfile.objects.select_related("profile_picture", "event").get(
        pk=speaker.pk
    )
    other_event = Event(
        name="Other",
        slug="other",
        organiser=event.organiser,
        email="other@example.com",
        locales=["en"],
        locale="en",
        date_from=event.date_from,
        date_to=event.date_to,
        custom_domain="https://explicit.example.com",
    )

    assert speaker.avatar == pic.avatar
    assert speaker.avatar_url == pic.avatar.url
    assert not speaker.avatar_url.startswith("http")
    assert speaker.get_avatar_url().startswith(settings.SITE_URL)
    assert speaker.get_avatar_url(event=other_event).startswith(
        "https://explicit.example.com"
    )

    event.custom_domain = "https://custom.example.com"
    event.save(update_fields=["custom_domain"])
    speaker = SpeakerProfile.objects.select_related("profile_picture", "event").get(
        pk=speaker.pk
    )
    assert speaker.get_avatar_url().startswith("https://custom.example.com")


def test_profile_picture_mixin_without_picture(event):
    speaker = SpeakerFactory(event=event)

    assert speaker.avatar is None
    assert speaker.avatar_url is None
    assert speaker.get_avatar_url() == ""
