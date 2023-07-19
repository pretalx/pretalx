# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 3.2.4 on 2021-08-30 23:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0007_auto_20190327_2241"),
    ]

    operations = [
        migrations.AddField(
            model_name="mailtemplate",
            name="is_auto_created",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="queuedmail",
            name="template",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mails",
                to="mail.mailtemplate",
            ),
        ),
    ]
