# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("person", "0041_attendeeprofile")]

    operations = [
        migrations.RenameField(
            model_name="userapitoken", old_name="events", new_name="limit_events"
        ),
        migrations.AlterField(
            model_name="userapitoken",
            name="limit_events",
            field=models.ManyToManyField(
                blank=True, related_name="+", to="event.event"
            ),
        ),
        migrations.AddField(
            model_name="userapitoken",
            name="all_events",
            field=models.BooleanField(default=False),
        ),
    ]
