# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import pretalx.common.models.mixins
import pretalx.person.models.picture


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0033_usereventpreferences"),
        ("event", "0041_event_og_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="speakerprofile",
            name="code",
            field=models.CharField(max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="speakerprofile",
            name="name",
            field=models.CharField(max_length=120, null=True),
        ),
        migrations.CreateModel(
            name="ProfilePicture",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "avatar",
                    models.ImageField(
                        null=True, upload_to=pretalx.person.models.picture.picture_path
                    ),
                ),
                (
                    "avatar_thumbnail",
                    models.ImageField(null=True, upload_to="avatars/"),
                ),
                (
                    "avatar_thumbnail_tiny",
                    models.ImageField(null=True, upload_to="avatars/"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pictures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
            bases=(pretalx.common.models.mixins.FileCleanupMixin, models.Model),
        ),
        migrations.AddField(
            model_name="speakerprofile",
            name="profile_picture",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="speakers",
                to="person.profilepicture",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="profile_picture",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="users",
                to="person.profilepicture",
            ),
        ),
    ]
