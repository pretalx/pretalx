# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0095_populate_speakerrole_speaker"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="speakerrole",
            unique_together={("submission", "speaker")},
        ),
        migrations.RemoveField(
            model_name="speakerrole",
            name="user",
        ),
        migrations.AlterField(
            model_name="speakerrole",
            name="speaker",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="speaker_roles",
                to="person.speakerprofile",
            ),
        ),
        migrations.AlterField(
            model_name="submission",
            name="speakers",
            field=models.ManyToManyField(
                blank=True,
                related_name="submissions",
                through="submission.SpeakerRole",
                to="person.speakerprofile",
                verbose_name="Speakers",
            ),
        ),
    ]
