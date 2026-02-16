# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0095_speakerprofile_data"),
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
        migrations.RemoveField(
            model_name="answer",
            name="person",
        ),
        migrations.RemoveField(
            model_name="feedback",
            name="speaker",
        ),
        migrations.RenameField(
            model_name="feedback",
            old_name="speaker_profile",
            new_name="speaker",
        ),
        migrations.AlterField(
            model_name="feedback",
            name="speaker",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="feedback",
                to="person.speakerprofile",
                verbose_name="Speaker",
            ),
        ),
    ]
