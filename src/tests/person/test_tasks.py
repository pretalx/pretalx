# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.person.models import ProfilePicture
from pretalx.person.tasks import clean_orphaned_profile_pictures


def _make_image(name="test.png"):
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01"
        b"\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return SimpleUploadedFile(name, data, content_type="image/png")


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_deletes_old_orphan(speaker):
    with scopes_disabled():
        pic = ProfilePicture.objects.create(user=speaker, avatar=_make_image())
        file_path = pic.avatar.name
        assert default_storage.exists(file_path)
        ProfilePicture.objects.filter(pk=pic.pk).update(
            updated=now() - dt.timedelta(days=31)
        )
    clean_orphaned_profile_pictures(sender=None)
    assert not ProfilePicture.objects.filter(pk=pic.pk).exists()
    assert not default_storage.exists(file_path)


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_keeps_recent_orphan(speaker):
    with scopes_disabled():
        pic = ProfilePicture.objects.create(user=speaker, avatar=_make_image())
        file_path = pic.avatar.name
        ProfilePicture.objects.filter(pk=pic.pk).update(
            updated=now() - dt.timedelta(days=10)
        )
    clean_orphaned_profile_pictures(sender=None)
    assert ProfilePicture.objects.filter(pk=pic.pk).exists()
    assert default_storage.exists(file_path)


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_keeps_user_referenced(speaker):
    with scopes_disabled():
        pic = ProfilePicture.objects.create(user=speaker, avatar=_make_image())
        file_path = pic.avatar.name
        speaker.profile_picture = pic
        speaker.save(update_fields=["profile_picture"])
        ProfilePicture.objects.filter(pk=pic.pk).update(
            updated=now() - dt.timedelta(days=31)
        )
    clean_orphaned_profile_pictures(sender=None)
    assert ProfilePicture.objects.filter(pk=pic.pk).exists()
    assert default_storage.exists(file_path)


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_keeps_speaker_referenced(speaker, event):
    with scopes_disabled():
        pic = ProfilePicture.objects.create(user=speaker, avatar=_make_image())
        file_path = pic.avatar.name
    with scope(event=event):
        profile = speaker.event_profile(event)
        profile.profile_picture = pic
        profile.save(update_fields=["profile_picture"])
    with scopes_disabled():
        ProfilePicture.objects.filter(pk=pic.pk).update(
            updated=now() - dt.timedelta(days=31)
        )
    clean_orphaned_profile_pictures(sender=None)
    assert ProfilePicture.objects.filter(pk=pic.pk).exists()
    assert default_storage.exists(file_path)
