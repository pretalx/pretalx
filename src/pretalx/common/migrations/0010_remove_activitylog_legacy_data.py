# SPDX-FileCopyrightText: 2026-present Tobias Kunze and contributors
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0009_activitylog_migrate_to_jsonfield"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="activitylog",
            name="legacy_data",
        ),
    ]
