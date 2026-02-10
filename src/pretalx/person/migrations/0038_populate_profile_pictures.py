# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import OuterRef, Subquery


def populate_profile_pictures(apps, schema_editor):
    User = apps.get_model("person", "User")
    ProfilePicture = apps.get_model("person", "ProfilePicture")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")

    users_with_avatars = (
        User.objects.exclude(avatar="").exclude(avatar="False").exclude(avatar=None)
    )

    pictures = []
    user_pks = []
    for user in users_with_avatars.iterator():
        pictures.append(
            ProfilePicture(
                user=user,
                avatar=user.avatar,
                avatar_thumbnail=user.avatar_thumbnail,
                avatar_thumbnail_tiny=user.avatar_thumbnail_tiny,
            )
        )
        user_pks.append(user.pk)

    ProfilePicture.objects.bulk_create(pictures)

    picture_subquery = Subquery(
        ProfilePicture.objects.filter(user_id=OuterRef("pk")).values("pk")[:1]
    )
    User.objects.filter(pk__in=user_pks).update(profile_picture=picture_subquery)

    profile_picture_subquery = Subquery(
        ProfilePicture.objects.filter(user_id=OuterRef("user_id")).values("pk")[:1]
    )
    SpeakerProfile.objects.filter(user_id__in=user_pks).update(
        profile_picture=profile_picture_subquery
    )


def reverse_populate_profile_pictures(apps, schema_editor):
    User = apps.get_model("person", "User")
    ProfilePicture = apps.get_model("person", "ProfilePicture")

    picture_qs = ProfilePicture.objects.filter(user_id=OuterRef("pk"))
    User.objects.filter(profile_picture__isnull=False).update(
        avatar=Subquery(picture_qs.values("avatar")[:1]),
        avatar_thumbnail=Subquery(picture_qs.values("avatar_thumbnail")[:1]),
        avatar_thumbnail_tiny=Subquery(picture_qs.values("avatar_thumbnail_tiny")[:1]),
        profile_picture=None,
    )

    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    SpeakerProfile.objects.update(profile_picture=None)
    ProfilePicture.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("person", "0037_profilepicture"),
    ]

    operations = [
        migrations.RunPython(
            populate_profile_pictures, reverse_populate_profile_pictures
        ),
    ]
