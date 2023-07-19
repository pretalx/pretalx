# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 3.2.16 on 2022-12-23 22:49

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0029_event_domain"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="content_locale_array",
            field=models.TextField(default="en"),
        ),
    ]
