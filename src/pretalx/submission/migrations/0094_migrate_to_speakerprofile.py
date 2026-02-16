# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0034_speakerprofile_and_profilepicture"),
        ("submission", "0093_speakerrole_position"),
    ]

    operations = [
        # SpeakerRole: add speaker FK, make user nullable
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
        # Answer: add speaker FK
        migrations.AddField(
            model_name="answer",
            name="speaker",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="answers",
                to="person.speakerprofile",
            ),
        ),
        # Feedback: add speaker_profile FK
        migrations.AddField(
            model_name="feedback",
            name="speaker_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="person.speakerprofile",
            ),
        ),
    ]
