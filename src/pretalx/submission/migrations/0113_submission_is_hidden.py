# SPDX-FileCopyrightText: 2026-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("submission", "0112_submission_submission_code_upper_idx")]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="is_hidden",
            field=models.BooleanField(default=False),
        )
    ]
