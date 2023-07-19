# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 2.0.2 on 2018-02-08 20:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0009_event_landing_page_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="plugins",
            field=models.TextField(blank=True, null=True),
        ),
    ]
