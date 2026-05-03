# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("person", "0038_user_created_backfill")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="created",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created"),
        )
    ]
