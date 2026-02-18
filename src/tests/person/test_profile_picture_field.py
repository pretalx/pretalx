# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import ValidationError
from django_scopes import scope, scopes_disabled

from pretalx.common.forms.fields import ProfilePictureField
from pretalx.common.forms.widgets import ProfilePictureWidget
from pretalx.person.models import ProfilePicture, SpeakerProfile


def _make_image(name="test.png", content_type="image/png"):
    # 1x1 red PNG
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01"
        b"\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return SimpleUploadedFile(name, data, content_type=content_type)


@pytest.fixture
def profile_picture(speaker):
    with scopes_disabled():
        return ProfilePicture.objects.create(user=speaker, avatar=_make_image())


@pytest.fixture
def speaker_with_picture(speaker_profile, event, profile_picture):
    with scope(event=event):
        speaker_profile.profile_picture = profile_picture
        speaker_profile.save(update_fields=["profile_picture"])
    return speaker_profile


@pytest.fixture
def other_profile_pictures(speaker):
    with scopes_disabled():
        pics = [
            ProfilePicture.objects.create(
                user=speaker, avatar=_make_image(f"pic{i}.png")
            )
            for i in range(2)
        ]
    return pics


@pytest.mark.django_db
def test_profile_picture_field_clean_keep():
    field = ProfilePictureField(required=False)
    result = field.clean({"action": "keep", "file": None})
    assert result is None


@pytest.mark.django_db
def test_profile_picture_field_clean_remove():
    field = ProfilePictureField(required=False)
    result = field.clean({"action": "remove", "file": None})
    assert result is False


@pytest.mark.django_db
def test_profile_picture_field_clean_select_valid(speaker, profile_picture):
    field = ProfilePictureField(user=speaker)
    result = field.clean({"action": f"select_{profile_picture.pk}", "file": None})
    assert result == profile_picture


@pytest.mark.django_db
def test_profile_picture_field_clean_select_invalid(
    speaker, other_speaker, profile_picture
):
    field = ProfilePictureField(user=other_speaker)
    with pytest.raises(ValidationError):
        field.clean({"action": f"select_{profile_picture.pk}", "file": None})


@pytest.mark.django_db
def test_profile_picture_field_clean_upload():
    field = ProfilePictureField()
    image = _make_image()
    result = field.clean({"action": "upload", "file": image})
    assert result == image


@pytest.mark.django_db
def test_profile_picture_field_clean_upload_invalid_type():
    field = ProfilePictureField()
    bad_file = SimpleUploadedFile("test.txt", b"not an image", "text/plain")
    with pytest.raises(ValidationError):
        field.clean({"action": "upload", "file": bad_file})


@pytest.mark.django_db
def test_profile_picture_field_require_prevents_remove():
    field = ProfilePictureField(required=True)
    with pytest.raises(ValidationError):
        field.clean({"action": "remove", "file": None})


@pytest.mark.django_db
def test_profile_picture_field_require_no_existing():
    field = ProfilePictureField(required=True, current_picture=None)
    with pytest.raises(ValidationError):
        field.clean({"action": "keep", "file": None})


@pytest.mark.django_db
def test_profile_picture_field_require_with_existing(profile_picture):
    field = ProfilePictureField(required=True, current_picture=profile_picture)
    result = field.clean({"action": "keep", "file": None})
    assert result is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("keep", False),
        ("remove", True),
        ("select_1", True),
        ("upload", True),
    ),
)
def test_profile_picture_field_has_changed(action, expected):
    field = ProfilePictureField()
    assert field.has_changed(None, {"action": action}) is expected


@pytest.mark.django_db
def test_profile_picture_field_save_none(speaker, speaker_profile, event):
    field = ProfilePictureField()
    field._cleaned_value = None
    with scope(event=event):
        field.save(speaker_profile, speaker)
        speaker_profile.refresh_from_db()
        assert speaker_profile.profile_picture is None


@pytest.mark.django_db
def test_profile_picture_field_save_remove(
    speaker_with_picture, event, profile_picture
):
    field = ProfilePictureField()
    field._cleaned_value = False
    with scope(event=event):
        assert speaker_with_picture.profile_picture == profile_picture
        old_updated = profile_picture.updated
        field.save(speaker_with_picture, speaker_with_picture.user)
        speaker_with_picture.refresh_from_db()
        assert speaker_with_picture.profile_picture is None
        speaker_with_picture.refresh_from_db()
        assert profile_picture.updated >= old_updated


@pytest.mark.django_db
def test_profile_picture_field_save_select(
    speaker, speaker_profile, event, profile_picture, other_profile_pictures
):
    field = ProfilePictureField()
    target = other_profile_pictures[0]
    field._cleaned_value = target
    with scope(event=event):
        field.save(speaker_profile, speaker)
        speaker_profile.refresh_from_db()
        assert speaker_profile.profile_picture == target
        speaker.refresh_from_db()
        assert speaker.profile_picture == target


@pytest.mark.django_db
def test_profile_picture_field_save_upload(speaker, speaker_profile, event):
    field = ProfilePictureField()
    image = _make_image()
    field._cleaned_value = image
    with scope(event=event):
        old_count = ProfilePicture.objects.filter(user=speaker).count()
        field.save(speaker_profile, speaker)
        speaker_profile.refresh_from_db()
        assert speaker_profile.profile_picture is not None
        assert ProfilePicture.objects.filter(user=speaker).count() == old_count + 1
        speaker.refresh_from_db()
        assert speaker.profile_picture == speaker_profile.profile_picture


@pytest.mark.django_db
def test_profile_picture_field_save_upload_bumps_old(
    speaker_with_picture, event, profile_picture
):
    field = ProfilePictureField()
    image = _make_image()
    field._cleaned_value = image
    old_updated = profile_picture.updated
    with scope(event=event):
        field.save(speaker_with_picture, speaker_with_picture.user)
        profile_picture.refresh_from_db()
        assert profile_picture.updated >= old_updated


@pytest.mark.django_db
def test_profile_picture_widget_no_user():
    widget = ProfilePictureWidget(user=None, current_picture=None)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})
    assert ctx["widget"]["other_pictures"] == []
    assert ctx["widget"]["current_picture"] is None


@pytest.mark.django_db
def test_profile_picture_widget_with_pictures(
    speaker, profile_picture, other_profile_pictures
):
    widget = ProfilePictureWidget(user=speaker, current_picture=profile_picture)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})
    # 3 pictures total: profile_picture + 2 other_profile_pictures
    assert len(ctx["widget"]["other_pictures"]) == 3


@pytest.mark.django_db
def test_profile_picture_widget_labels_single_event(
    speaker, event, speaker_with_picture, profile_picture
):
    widget = ProfilePictureWidget(user=speaker, current_picture=None)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})
    pics = ctx["widget"]["other_pictures"]
    # profile_picture is linked to speaker's profile in this event
    linked = [p for p in pics if p["pk"] == profile_picture.pk]
    assert len(linked) == 1
    assert linked[0]["label"] == str(event.name)


@pytest.mark.django_db
def test_profile_picture_widget_labels_multiple_events(
    speaker, event, other_event, speaker_with_picture, profile_picture
):
    with scopes_disabled():
        other_profile = SpeakerProfile.objects.create(user=speaker, event=other_event)
        other_profile.profile_picture = profile_picture
        other_profile.save(update_fields=["profile_picture"])
    widget = ProfilePictureWidget(user=speaker, current_picture=None)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})
    pics = ctx["widget"]["other_pictures"]
    linked = [p for p in pics if p["pk"] == profile_picture.pk]
    assert len(linked) == 1
    assert "2" in linked[0]["label"]


@pytest.mark.django_db
def test_profile_picture_widget_current_highlighted(speaker, profile_picture):
    widget = ProfilePictureWidget(user=speaker, current_picture=profile_picture)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})
    pics = ctx["widget"]["other_pictures"]
    current = [p for p in pics if p["pk"] == profile_picture.pk]
    assert len(current) == 1
    assert current[0]["is_current"] is True


@pytest.mark.django_db
def test_profile_picture_widget_upload_only(
    speaker, profile_picture, other_profile_pictures
):
    widget = ProfilePictureWidget(
        user=speaker, current_picture=profile_picture, upload_only=True
    )
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})
    assert ctx["widget"]["other_pictures"] == []
    assert ctx["widget"]["current_picture"] is not None


@pytest.mark.django_db
def test_profile_picture_field_upload_only_rejects_select(speaker, profile_picture):
    field = ProfilePictureField(user=speaker, upload_only=True)
    with pytest.raises(ValidationError):
        field.clean({"action": f"select_{profile_picture.pk}", "file": None})


@pytest.mark.django_db
def test_orga_edit_speaker_upload_avatar(
    orga_client, speaker, speaker_profile, event, submission
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
    image = _make_image()
    response = orga_client.post(
        url,
        data={
            "name": speaker_profile.name,
            "email": speaker.email,
            "biography": "bio",
            "avatar_action": "upload",
            "avatar": image,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_profile.refresh_from_db()
        assert speaker_profile.profile_picture is not None


@pytest.mark.django_db
def test_orga_edit_speaker_select_existing_picture(
    orga_client,
    speaker_with_picture,
    event,
    submission,
    other_profile_pictures,
    profile_picture,
):
    target = other_profile_pictures[0]
    with scope(event=event):
        url = speaker_with_picture.orga_urls.base
    response = orga_client.post(
        url,
        data={
            "name": speaker_with_picture.name,
            "email": speaker_with_picture.user.email,
            "biography": "bio",
            "avatar_action": f"select_{target.pk}",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_with_picture.refresh_from_db()
        # Orga cannot select from speaker's picture library — picture stays unchanged
        assert speaker_with_picture.profile_picture == profile_picture


@pytest.mark.django_db
def test_orga_edit_speaker_remove_avatar(
    orga_client, speaker_with_picture, event, submission
):
    with scope(event=event):
        url = speaker_with_picture.orga_urls.base
    response = orga_client.post(
        url,
        data={
            "name": speaker_with_picture.name,
            "email": speaker_with_picture.user.email,
            "biography": "bio",
            "avatar_action": "remove",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_with_picture.refresh_from_db()
        assert speaker_with_picture.profile_picture is None


@pytest.mark.django_db
def test_orga_edit_speaker_avatar_no_change(
    orga_client, speaker_with_picture, event, submission, profile_picture
):
    with scope(event=event):
        url = speaker_with_picture.orga_urls.base
    response = orga_client.post(
        url,
        data={
            "name": speaker_with_picture.name,
            "email": speaker_with_picture.user.email,
            "biography": "bio",
            "avatar_action": "keep",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_with_picture.refresh_from_db()
        assert speaker_with_picture.profile_picture == profile_picture


@pytest.mark.django_db
def test_orga_edit_speaker_avatar_not_shown_when_disabled(
    orga_client, speaker_profile, event, submission
):
    with scopes_disabled():
        fields = event.cfp.fields.copy()
        fields["avatar"]["visibility"] = "do_not_ask"
        event.cfp.fields = fields
        event.cfp.save(update_fields=["fields"])
    with scope(event=event):
        url = speaker_profile.orga_urls.base
    response = orga_client.get(url, follow=True)
    assert response.status_code == 200
    assert "pp-widget" not in response.text
