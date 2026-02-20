# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0098_migrate_access_code_fks_to_m2m"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="submitteraccesscode",
            name="submission_type",
        ),
        migrations.RemoveField(
            model_name="submitteraccesscode",
            name="track",
        ),
        migrations.AlterField(
            model_name="submitteraccesscode",
            name="submission_types",
            field=models.ManyToManyField(
                related_name="submitter_access_codes", to="submission.submissiontype"
            ),
        ),
        migrations.AlterField(
            model_name="submitteraccesscode",
            name="tracks",
            field=models.ManyToManyField(
                related_name="submitter_access_codes", to="submission.track"
            ),
        ),
    ]
