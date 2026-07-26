# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("submission", "0108_alter_resource_description")]

    operations = [
        migrations.AlterField(
            model_name="submission",
            name="title",
            field=models.CharField(max_length=1000),
        )
    ]
