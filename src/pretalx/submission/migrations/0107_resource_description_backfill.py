# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pathlib import Path

from django.db import migrations
from django_scopes import scopes_disabled


def backfill_description(apps, schema_editor):
    Resource = apps.get_model("submission", "Resource")
    with scopes_disabled():
        empty = Resource.objects.filter(
            description__isnull=True
        ) | Resource.objects.filter(description="")
        for resource in empty.distinct():
            file_name = resource.resource.name if resource.resource else ""
            if file_name:
                resource.description = Path(file_name).name
            elif resource.link:
                resource.description = resource.link
            else:
                resource.description = "Resource"
            resource.save(update_fields=["description"])


class Migration(migrations.Migration):
    dependencies = [("submission", "0106_attendee_signup")]

    operations = [migrations.RunPython(backfill_description, migrations.RunPython.noop)]
