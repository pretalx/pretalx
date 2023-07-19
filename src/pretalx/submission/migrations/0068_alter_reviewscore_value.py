# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 3.2.10 on 2022-04-06 10:25

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0067_question_extra_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reviewscore",
            name="value",
            field=models.DecimalField(decimal_places=2, max_digits=7),
        ),
    ]
