# SPDX-FileCopyrightText: 2025-present Tobias Kunze and contributors
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0008_remove_daft_logs"),
    ]

    operations = [
        migrations.RenameField(
            model_name="activitylog",
            old_name="data",
            new_name="legacy_data",
        ),
        migrations.AddField(
            model_name="activitylog",
            name="data",
            field=models.JSONField(blank=True, null=True, default=dict),
        ),
    ]
