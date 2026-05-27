# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("submission", "0107_resource_description_backfill")]

    operations = [
        migrations.AlterField(
            model_name="resource",
            name="description",
            field=models.CharField(max_length=1000, verbose_name="Description"),
        )
    ]
