# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0044_event_locales_json"),
        ("person", "0042_userapitoken_all_events"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="usereventpreferences", unique_together=set()
        ),
        migrations.AlterField(
            model_name="usereventpreferences",
            name="event",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_preferences",
                to="event.event",
            ),
        ),
        migrations.AddConstraint(
            model_name="usereventpreferences",
            constraint=models.UniqueConstraint(
                fields=("user", "event"), name="unique_user_event_preferences"
            ),
        ),
        migrations.AddConstraint(
            model_name="usereventpreferences",
            constraint=models.UniqueConstraint(
                condition=models.Q(("event__isnull", True)),
                fields=("user",),
                name="unique_user_global_preferences",
            ),
        ),
    ]
