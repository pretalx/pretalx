# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 1.11.5 on 2017-10-04 21:42

from django.db import migrations, models
import pretalx.event.models.event


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0007_auto_20170924_0505"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="logo",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=pretalx.event.models.event.event_logo_path,
            ),
        ),
    ]
