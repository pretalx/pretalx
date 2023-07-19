# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 1.10.7 on 2017-04-29 15:18

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import i18nfield.fields
import pretalx.common.mixins


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("event", "0002_auto_20170429_1018"),
        ("submission", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Availability",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("start", models.DateTimeField()),
                ("end", models.DateTimeField()),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="availabilities",
                        to="event.Event",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="availabilities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            bases=(pretalx.common.mixins.models.LogMixin, models.Model),
        ),
        migrations.CreateModel(
            name="Room",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("name", i18nfield.fields.I18nCharField(max_length=100)),
                (
                    "description",
                    i18nfield.fields.I18nCharField(
                        blank=True, max_length=1000, null=True
                    ),
                ),
                ("capacity", models.PositiveIntegerField(blank=True, null=True)),
                ("position", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rooms",
                        to="event.Event",
                    ),
                ),
            ],
            bases=(pretalx.common.mixins.models.LogMixin, models.Model),
        ),
        migrations.CreateModel(
            name="Schedule",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("version", models.CharField(blank=True, max_length=190, null=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="schedules",
                        to="event.Event",
                    ),
                ),
            ],
            bases=(pretalx.common.mixins.models.LogMixin, models.Model),
        ),
        migrations.CreateModel(
            name="TalkSlot",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("start", models.DateTimeField()),
                ("end", models.DateTimeField()),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="talks",
                        to="schedule.Room",
                    ),
                ),
                (
                    "schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="talks",
                        to="schedule.Schedule",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="slots",
                        to="submission.Submission",
                    ),
                ),
            ],
            bases=(pretalx.common.mixins.models.LogMixin, models.Model),
        ),
    ]
