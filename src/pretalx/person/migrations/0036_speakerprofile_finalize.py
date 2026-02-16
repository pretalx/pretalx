# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0035_speakerprofile_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="speakerprofile",
            name="code",
            field=models.CharField(max_length=16),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name="speakerprofile",
            unique_together={("event", "code"), ("event", "user")},
        ),
        migrations.RemoveField(
            model_name="user",
            name="avatar",
        ),
        migrations.RemoveField(
            model_name="user",
            name="avatar_thumbnail",
        ),
        migrations.RemoveField(
            model_name="user",
            name="avatar_thumbnail_tiny",
        ),
        migrations.RemoveField(
            model_name="user",
            name="get_gravatar",
        ),
    ]
