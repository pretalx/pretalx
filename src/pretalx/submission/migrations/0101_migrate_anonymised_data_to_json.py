# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json

from django.db import migrations


def migrate_anonymised_data(apps, schema_editor):
    Submission = apps.get_model("submission", "Submission")
    for submission in Submission.objects.exclude(anonymised_data__isnull=True).exclude(
        anonymised_data__in=("", "{}")
    ):
        try:
            data = json.loads(submission.anonymised_data)
        except (ValueError, TypeError):
            continue
        if data and isinstance(data, dict):
            submission.anonymised = data
            submission.save(update_fields=["anonymised"])


class Migration(migrations.Migration):
    dependencies = [("submission", "0100_submission_anonymised")]

    operations = [
        migrations.RunPython(migrate_anonymised_data, migrations.RunPython.noop)
    ]
