# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("submission", "0102_remove_submission_anonymised_data")]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="draft_additional_speakers",
            field=models.JSONField(blank=True, default=list),
        )
    ]
