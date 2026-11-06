# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import Q

BATCH_SIZE = 1000
RENAMES = {
    "QuestionTable-sessions": "SubmissionQuestionTable",
    "QuestionTable-speakers": "SpeakerQuestionTable",
    "QuestionTable-reviews": "ReviewerQuestionTable",
}
COLUMN_RENAMES = {
    "OutboxMailTable": {"template_info": "template_role", "status_display": "state"},
    "SentMailTable": {"template_info": "template_role", "status_display": "state"},
}


def _rename_column_names(entry, mapping):
    changed = False
    for key in ("columns", "ordering"):
        values = entry.get(key)
        if not isinstance(values, list):
            continue
        result = []
        for value in values:
            if not isinstance(value, str):
                result.append(value)
                continue
            prefix = "-" if value.startswith("-") else ""
            new = prefix + mapping.get(value.removeprefix("-"), value.removeprefix("-"))
            changed = changed or new != value
            if new not in result:
                result.append(new)
        entry[key] = result
    return changed


def rename_table_keys(preferences, renames, column_renames=None):
    tables = preferences.get("tables")
    if not isinstance(tables, dict):
        return False
    changed = False
    for table, mapping in (column_renames or {}).items():
        if isinstance(tables.get(table), dict):
            changed = _rename_column_names(tables[table], mapping) or changed
    for old, new in renames.items():
        if old in tables:
            value = tables.pop(old)
            tables.setdefault(new, value)
            changed = True
    return changed


def rename_preferences(apps, renames, column_renames):
    UserEventPreferences = apps.get_model("person", "UserEventPreferences")
    queryset = UserEventPreferences.objects.filter(
        Q(preferences__tables__has_any_keys=list(renames))
        | Q(preferences__tables__has_any_keys=list(column_renames))
    )
    batch = []
    for entry in queryset.iterator(chunk_size=BATCH_SIZE):
        if rename_table_keys(entry.preferences, renames, column_renames):
            batch.append(entry)
        if len(batch) >= BATCH_SIZE:
            UserEventPreferences.objects.bulk_update(batch, ["preferences"])
            batch = []
    if batch:
        UserEventPreferences.objects.bulk_update(batch, ["preferences"])


def forwards(apps, schema_editor):
    rename_preferences(apps, RENAMES, COLUMN_RENAMES)


def backwards(apps, schema_editor):
    rename_preferences(
        apps,
        {new: old for old, new in RENAMES.items()},
        {
            table: {new: old for old, new in mapping.items()}
            for table, mapping in COLUMN_RENAMES.items()
        },
    )


class Migration(migrations.Migration):
    dependencies = [("person", "0050_user_lookup_indexes")]

    operations = [migrations.RunPython(forwards, backwards)]
