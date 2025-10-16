# SPDX-FileCopyrightText: 2025-present Tobias Kunze and contributors
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations


def remove_draft_logs(apps, schema_editor):
    ActivityLog = apps.get_model("common", "ActivityLog")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Submission = apps.get_model("submission", "Submission")
    ActivityLog.objects.all().filter(
        content_type=ContentType.objects.get_for_model(Submission),
        object_id__in=Submission._base_manager.filter(state="draft"),
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0007_alter_globalsettings_settingsstore_unique_together"),
        ("submission", "0086_alter_question_icon"),
    ]

    operations = [migrations.RunPython(remove_draft_logs, migrations.RunPython.noop)]
