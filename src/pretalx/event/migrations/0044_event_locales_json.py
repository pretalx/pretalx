# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models

import pretalx.event.models.event


def migrate_locale_arrays(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    for event in Event.objects.all():
        event.locales = (event.locale_array or "en").split(",")
        event.content_locales = (event.content_locale_array or "en").split(",")
        event.save(update_fields=["locales", "content_locales"])


def unmigrate_locale_arrays(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    for event in Event.objects.all():
        event.locale_array = ",".join(event.locales)
        event.content_locale_array = ",".join(event.content_locales)
        event.save(update_fields=["locale_array", "content_locale_array"])


class Migration(migrations.Migration):
    dependencies = [("event", "0043_event_attendee_signup_settings")]

    operations = [
        migrations.AddField(
            model_name="event",
            name="locales",
            field=models.JSONField(default=pretalx.event.models.event.default_locales),
        ),
        migrations.AddField(
            model_name="event",
            name="content_locales",
            field=models.JSONField(default=pretalx.event.models.event.default_locales),
        ),
        migrations.RunPython(migrate_locale_arrays, unmigrate_locale_arrays),
        migrations.RemoveField(model_name="event", name="locale_array"),
        migrations.RemoveField(model_name="event", name="content_locale_array"),
    ]
