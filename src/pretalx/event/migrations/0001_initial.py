# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 1.10.7 on 2017-04-29 15:18

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import i18nfield.fields
import pretalx.common.mixins


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("name", i18nfield.fields.I18nCharField(max_length=200)),
                (
                    "slug",
                    models.SlugField(
                        validators=[
                            django.core.validators.RegexValidator(
                                message="The slug may only contain letters, numbers, dots and dashes.",
                                regex="^[a-zA-Z0-9.-]+$",
                            )
                        ]
                    ),
                ),
                (
                    "subtitle",
                    i18nfield.fields.I18nCharField(
                        blank=True, max_length=200, null=True
                    ),
                ),
                ("is_public", models.BooleanField(default=False)),
                ("date_from", models.DateField(blank=True, null=True)),
                ("date_to", models.DateField(blank=True, null=True)),
                ("timezone", models.CharField(default="UTC", max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("color", models.CharField(blank=True, max_length=7, null=True)),
                ("locale_array", models.TextField(default="en")),
                ("locale", models.CharField(default="en", max_length=32)),
            ],
            bases=(pretalx.common.mixins.models.LogMixin, models.Model),
        ),
        migrations.CreateModel(
            name="Event_SettingsStore",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("key", models.CharField(max_length=255)),
                ("value", models.TextField()),
                (
                    "object",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="_settings_objects",
                        to="event.Event",
                    ),
                ),
            ],
        ),
    ]
