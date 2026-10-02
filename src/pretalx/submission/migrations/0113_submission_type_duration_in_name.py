# SPDX-FileCopyrightText: 2026-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.utils.translation import gettext as _
from django.utils.translation import override
from django_scopes import scopes_disabled


def format_name(name, duration):
    """migrate the former SubmissionType default duration suffix formatting"""
    if not duration:
        return name
    if duration >= 60 * 24:
        days = round(duration / 60 / 24, 1)
        if days == 1:
            return _("{name} (1 day)").format(name=name, duration=1)
        return _("{name} ({duration} days)").format(
            name=name, duration=int(days) if int(days) == days else days
        )
    if duration > 90:
        hours, minutes = divmod(duration, 60)
        if hours == 1:
            label = _("1 hour, {minutes} minutes").format(minutes=minutes)
        elif minutes:
            label = _("{hours} hours, {minutes} minutes").format(
                hours=hours, minutes=minutes
            )
        else:
            label = _("{hours} hours").format(hours=hours)
        return f"{name} ({label})"
    return _("{name} ({duration} minutes)").format(name=name, duration=duration)


def migrate_names(apps, schema_editor):
    SubmissionType = apps.get_model("submission", "SubmissionType")
    CfP = apps.get_model("submission", "CfP")
    database = schema_editor.connection.alias
    with scopes_disabled():
        required_events = CfP.objects.using(database).filter(
            fields__duration__visibility="required"
        )
        submission_types = (
            SubmissionType.objects.using(database)
            .exclude(event_id__in=required_events.values("event_id"))
            .exclude(default_duration=0)
            .select_related("event")
        )
        for submission_type in submission_types.iterator():
            if not submission_type.name:
                continue
            translations = submission_type.name.data
            if isinstance(translations, str):
                translations = dict.fromkeys(
                    submission_type.event.locales or [submission_type.event.locale],
                    translations,
                )
            names = {}
            for locale, name in translations.items():
                if not name:
                    continue
                with override(locale):
                    suffix = format_name("", submission_type.default_duration)
                    names[locale] = (
                        name
                        if name.endswith(suffix)
                        else format_name(name, submission_type.default_duration)
                    )
            if any(len(name) > 100 for name in names.values()):
                continue
            SubmissionType.objects.using(database).filter(pk=submission_type.pk).update(
                name=names
            )


class Migration(migrations.Migration):
    dependencies = [("submission", "0112_submission_submission_code_upper_idx")]

    operations = [migrations.RunPython(migrate_names, migrations.RunPython.noop)]
