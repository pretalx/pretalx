# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 3.1.4 on 2021-06-24 17:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0056_reviewscorecategory_is_independent"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="freeze_after",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="question_required",
            field=models.CharField(default="optional", max_length=14),
        ),
    ]
