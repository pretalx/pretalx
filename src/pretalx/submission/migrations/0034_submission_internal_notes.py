# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 2.1.5 on 2019-03-04 23:17

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0033_submission_slot_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="internal_notes",
            field=models.TextField(blank=True, null=True),
        ),
    ]
