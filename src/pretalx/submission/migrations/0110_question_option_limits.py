# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("submission", "0109_alter_submission_title")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="max_options",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="min_options",
            field=models.PositiveIntegerField(null=True),
        ),
    ]
