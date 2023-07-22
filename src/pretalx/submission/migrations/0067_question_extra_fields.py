# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 3.2.10 on 2022-03-17 02:24

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0066_submission_assignments"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="max_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="max_datetime",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="max_number",
            field=models.DecimalField(decimal_places=6, max_digits=16, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="min_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="min_datetime",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="min_number",
            field=models.DecimalField(decimal_places=6, max_digits=16, null=True),
        ),
    ]
