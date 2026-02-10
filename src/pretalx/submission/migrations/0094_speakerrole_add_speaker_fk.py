# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0039_remove_user_avatar_fields"),
        ("submission", "0093_speakerrole_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="speakerrole",
            name="speaker",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="person.speakerprofile",
            ),
        ),
        migrations.AlterField(
            model_name="speakerrole",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="speaker_roles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
