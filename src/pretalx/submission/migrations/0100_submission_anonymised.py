# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0099_remove_submitteraccesscode_submission_type_and_more")
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="anonymised",
            field=models.JSONField(null=True, blank=True),
        )
    ]
