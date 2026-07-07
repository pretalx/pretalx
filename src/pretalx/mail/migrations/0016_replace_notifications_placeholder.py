# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import Q

OLD = "{notifications}"
NEW = "{speaker_schedule_new}"


def _replace(value):
    data = getattr(value, "data", value)
    if isinstance(data, dict):
        return {
            key: entry.replace(OLD, NEW) if isinstance(entry, str) else entry
            for key, entry in data.items()
        }
    if isinstance(data, str):
        return data.replace(OLD, NEW)
    return data


def replace_notifications_placeholder(apps, schema_editor):
    MailTemplate = apps.get_model("mail", "MailTemplate")
    templates = MailTemplate.objects.filter(
        Q(subject__contains=OLD) | Q(text__contains=OLD)
    )
    for template in templates:
        template.subject = _replace(template.subject)
        template.text = _replace(template.text)
        template.save(update_fields=["subject", "text"])


class Migration(migrations.Migration):
    dependencies = [("mail", "0015_queuedmail_text_html")]

    operations = [
        migrations.RunPython(
            replace_notifications_placeholder, migrations.RunPython.noop
        )
    ]
