# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 1.11.8 on 2017-12-15 22:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0010_eventpermission_review_override_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="speakerprofile",
            name="has_arrived",
            field=models.BooleanField(default=False),
        ),
    ]
