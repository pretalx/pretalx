import pytest
from django.conf import settings
from django_scopes import scopes_disabled

from pretalx.person.models import User
from pretalx.person.models.picture import ProfilePicture, picture_path
from tests.factories import SpeakerFactory, UserFactory

pytestmark = pytest.mark.unit


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


@pytest.mark.django_db
def test_profile_picture_str():
    user = UserFactory()
    pic = ProfilePicture(user=user)
    assert str(pic) == f"ProfilePicture(user={user.code})"


@pytest.mark.parametrize(
    ("with_avatar", "expected"),
    ((True, True), (False, False)),
    ids=["with_avatar", "without_avatar"],
)
@pytest.mark.django_db
def test_profile_picture_has_avatar(make_image, with_avatar, expected):
    user = UserFactory()
    kwargs = {"avatar": make_image()} if with_avatar else {}
    pic = ProfilePicture.objects.create(user=user, **kwargs)
    assert pic.has_avatar is expected


@pytest.mark.django_db
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
@pytest.mark.django_db
def test_profile_picture_avatar_url(make_image, with_avatar, has_url):
    user = UserFactory()
    kwargs = {"avatar": make_image()} if with_avatar else {}
    pic = ProfilePicture.objects.create(user=user, **kwargs)
    if has_url:
        assert pic.avatar_url == pic.avatar.url
    else:
        assert pic.avatar_url is None


@pytest.mark.django_db
def test_profile_picture_get_avatar_url_no_avatar():
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user)
    assert pic.get_avatar_url() == ""


@pytest.mark.django_db
def test_profile_picture_get_avatar_url_default(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    url = pic.get_avatar_url()
    assert url.startswith(settings.SITE_URL)


@pytest.mark.parametrize(
    ("custom_domain", "expected_prefix"),
    (("https://custom.example.com", "https://custom.example.com"), (None, None)),
    ids=["with_custom_domain", "without_custom_domain"],
)
@pytest.mark.django_db
def test_profile_picture_get_avatar_url_event_domain(
    make_image, event, custom_domain, expected_prefix
):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    event.custom_domain = custom_domain
    url = pic.get_avatar_url(event=event)
    assert url.startswith(expected_prefix or settings.SITE_URL)


@pytest.mark.parametrize("thumbnail", ("tiny", "default"))
@pytest.mark.django_db
def test_profile_picture_get_avatar_url_thumbnail_fallback(make_image, thumbnail):
    """When a thumbnail doesn't exist, create_thumbnail generates one on the fly."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    result = pic.get_avatar_url(thumbnail=thumbnail)

    assert result.startswith(settings.SITE_URL)


@pytest.mark.parametrize(
    ("thumbnail", "field_name", "file_name"),
    (
        ("tiny", "avatar_thumbnail_tiny", "tiny.png"),
        ("default", "avatar_thumbnail", "thumb.png"),
    ),
)
@pytest.mark.django_db
def test_profile_picture_get_avatar_url_thumbnail_exists(
    make_image, thumbnail, field_name, file_name
):
    """When a thumbnail already exists, it's used directly."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(
        user=user, avatar=make_image(), **{field_name: make_image(file_name)}
    )
    url = pic.get_avatar_url(thumbnail=thumbnail)
    assert url.startswith(settings.SITE_URL)


@pytest.mark.django_db
def test_profile_picture_get_avatar_url_unknown_thumbnail_size(make_image):
    """An unknown thumbnail size causes create_thumbnail to return None."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    result = pic.get_avatar_url(thumbnail="nonexistent_size")
    assert result is None


@pytest.mark.django_db
def test_profile_picture_mixin_avatar_with_picture(make_image, event):
    """ProfilePictureMixin.avatar returns the avatar from the linked picture."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        speaker.profile_picture = pic
        speaker.save(update_fields=["profile_picture"])
        speaker = type(speaker).objects.get(pk=speaker.pk)
    assert speaker.avatar == pic.avatar


@pytest.mark.django_db
def test_profile_picture_mixin_avatar_without_picture(event):
    speaker = SpeakerFactory(event=event)
    assert speaker.avatar is None


@pytest.mark.django_db
def test_profile_picture_mixin_avatar_url_with_picture(make_image, event):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        speaker.profile_picture = pic
        speaker.save(update_fields=["profile_picture"])
        speaker = type(speaker).objects.get(pk=speaker.pk)
    assert speaker.avatar_url.startswith(settings.SITE_URL)


@pytest.mark.django_db
def test_profile_picture_mixin_avatar_url_without_picture(event):
    speaker = SpeakerFactory(event=event)
    assert speaker.avatar_url is None


@pytest.mark.django_db
def test_profile_picture_mixin_set_avatar(make_image, event):
    """set_avatar creates a new ProfilePicture and links it."""
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)

    with scopes_disabled():
        new_pic = speaker.set_avatar(make_image())

    assert new_pic is not None
    speaker.refresh_from_db()
    assert speaker.profile_picture == new_pic
    user.refresh_from_db()
    assert user.profile_picture == new_pic


@pytest.mark.django_db
def test_profile_picture_mixin_set_avatar_bumps_old_picture(make_image, event):
    """When replacing an avatar, the old picture gets its updated field bumped."""
    user = UserFactory()
    old_pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        speaker.profile_picture = old_pic
        speaker.save(update_fields=["profile_picture"])
    old_updated = old_pic.updated

    with scopes_disabled():
        new_pic = speaker.set_avatar(make_image("new.png"))

    old_pic.refresh_from_db()
    assert old_pic.updated >= old_updated
    assert speaker.profile_picture == new_pic


@pytest.mark.django_db
def test_profile_picture_mixin_set_avatar_user_already_has_picture(make_image, event):
    """When user already has a profile_picture, set_avatar doesn't override it."""
    user = UserFactory()
    existing_pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    user.profile_picture = existing_pic
    user.save(update_fields=["profile_picture"])
    speaker = SpeakerFactory(event=event, user=user)

    with scopes_disabled():
        speaker.set_avatar(make_image("new.png"))

    user.refresh_from_db()
    assert user.profile_picture == existing_pic
