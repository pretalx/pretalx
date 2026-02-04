# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models
from django.db.models import F


def populate_position(apps, schema_editor):
    SpeakerRole = apps.get_model("submission", "SpeakerRole")
    SpeakerRole.objects.update(position=F("user_id"))


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0092_delete_soft_deleted_submissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="speakerrole",
            name="position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(populate_position, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="speakerrole",
            options={"ordering": ("position",)},
        ),
    ]
