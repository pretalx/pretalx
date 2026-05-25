# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings

from pretalx.person.models import User
from pretalx.person.models.picture import ProfilePicture, picture_path
from tests.factories import ProfilePictureFactory, SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("code", "expected_name"),
    (("ABCDEF", "ABCDEF"), (None, "avatar")),
    ids=["with_code", "without_code"],
)
def test_picture_path(code, expected_name):
    user = User()
    user.code = code
    pic = ProfilePicture(user=user)
    path = picture_path(pic, "photo.jpg")

    assert path.startswith(f"avatars/{expected_name}_")
    assert path.endswith(".jpg")


def test_profile_picture_str():
    user = UserFactory()
    pic = ProfilePicture(user=user)
    assert str(pic) == f"ProfilePicture(user={user.code})"


@pytest.mark.parametrize(
    ("with_avatar", "expected"),
    ((True, True), (False, False)),
    ids=["with_avatar", "without_avatar"],
)
def test_profile_picture_has_avatar(make_image, with_avatar, expected):
    user = UserFactory()
    kwargs = {"avatar": make_image()} if with_avatar else {}
    pic = ProfilePictureFactory(user=user, **kwargs)
    assert pic.has_avatar is expected


def test_profile_picture_has_avatar_false_when_string_false():
    """Legacy data might store 'False' as avatar value."""
    user = UserFactory()
    pic = ProfilePicture(user=user)
    pic.avatar = "False"
    assert pic.has_avatar is False


@pytest.mark.parametrize(
    ("with_avatar", "has_url"),
    ((True, True), (False, False)),
    ids=["with_avatar", "without_avatar"],
)
def test_profile_picture_avatar_url(make_image, with_avatar, has_url):
    user = UserFactory()
    kwargs = {"avatar": make_image()} if with_avatar else {}
    pic = ProfilePictureFactory(user=user, **kwargs)
    if has_url:
        assert pic.avatar_url == pic.avatar.url
    else:
        assert pic.avatar_url is None


def test_profile_picture_get_avatar_url_no_avatar():
    user = UserFactory()
    pic = ProfilePictureFactory(user=user)
    assert pic.get_avatar_url() == ""


def test_profile_picture_get_avatar_url_default(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    url = pic.get_avatar_url()
    assert url.startswith(settings.SITE_URL)


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
    """When a thumbnail already exists, it's used directly."""
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


def test_profile_picture_mixin_avatar_with_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    speaker = type(speaker).objects.get(pk=speaker.pk)
    assert speaker.avatar == pic.avatar


def test_profile_picture_mixin_avatar_without_picture(event):
    speaker = SpeakerFactory(event=event)
    assert speaker.avatar is None


def test_profile_picture_mixin_avatar_url_with_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    speaker = type(speaker).objects.get(pk=speaker.pk)

    assert speaker.avatar_url == pic.avatar.url
    assert not speaker.avatar_url.startswith("http")


def test_profile_picture_mixin_avatar_url_without_picture(event):
    speaker = SpeakerFactory(event=event)
    assert speaker.avatar_url is None


def test_profile_picture_mixin_get_avatar_url_defaults_to_self_event(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    event.custom_domain = "https://custom.example.com"
    event.save(update_fields=["custom_domain"])
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    speaker = type(speaker).objects.get(pk=speaker.pk)

    assert speaker.get_avatar_url().startswith("https://custom.example.com")


def test_profile_picture_mixin_get_avatar_url_falls_back_to_site_url(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    speaker = type(speaker).objects.get(pk=speaker.pk)

    assert speaker.get_avatar_url().startswith(settings.SITE_URL)


def test_profile_picture_mixin_get_avatar_url_uses_explicit_event(make_image, event):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    speaker.profile_picture = pic
    speaker.save(update_fields=["profile_picture"])
    speaker = type(speaker).objects.get(pk=speaker.pk)

    other_event = type(event)(
        name="Other",
        slug="other",
        organiser=event.organiser,
        email="other@example.com",
        locale_array="en",
        locale="en",
        date_from=event.date_from,
        date_to=event.date_to,
        custom_domain="https://explicit.example.com",
    )

    url = speaker.get_avatar_url(event=other_event)

    assert url.startswith("https://explicit.example.com")


def test_profile_picture_mixin_get_avatar_url_without_picture(event):
    speaker = SpeakerFactory(event=event)
    assert speaker.get_avatar_url() == ""
