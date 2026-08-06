# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django.db import migrations

BATCH_SIZE = 1000


def rename_change_key(apps, key_from, key_to):
    # Historic speaker profile change logs recorded the account email under
    # the "email" key; that key now holds the profile contact email, so the
    # old entries move their value to "user_email". The filters double as
    # the cheap no-op fast path: untouched or already-migrated entries are
    # never loaded.
    ActivityLog = apps.get_model("common", "ActivityLog")
    queryset = ActivityLog.objects.filter(
        action_type="pretalx.user.profile.update", data__changes__has_key=key_from
    ).exclude(data__changes__has_key=key_to)
    batch = []
    for entry in queryset.iterator(chunk_size=BATCH_SIZE):
        changes = entry.data["changes"]
        changes[key_to] = changes.pop(key_from)
        batch.append(entry)
        if len(batch) >= BATCH_SIZE:
            ActivityLog.objects.bulk_update(batch, ["data"])
            batch = []
    if batch:
        ActivityLog.objects.bulk_update(batch, ["data"])


def account_email_to_user_email(apps, schema_editor):
    rename_change_key(apps, "email", "user_email")


def user_email_to_account_email(apps, schema_editor):
    rename_change_key(apps, "user_email", "email")


def mail_logs_users_to_speakers(apps, schema_editor):
    # Historic pretalx.mail.sent data contained to_users as (pk, email) pairs.
    # With the recipient M2M dropped, they become to_speakers pairs via the
    # entry's event profile, and unresolved ones fold into the address list.
    ActivityLog = apps.get_model("common", "ActivityLog")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    queryset = ActivityLog.objects.filter(
        action_type="pretalx.mail.sent", data__has_key="to_users"
    ).order_by("pk")
    last_pk = 0
    while batch := list(queryset.filter(pk__gt=last_pk)[:BATCH_SIZE]):
        last_pk = batch[-1].pk
        wanted_users = set()
        wanted_events = set()
        for entry in batch:
            for pair in entry.data.get("to_users") or []:
                wanted_users.add(pair[0])
                if entry.event_id:
                    wanted_events.add(entry.event_id)
        profiles = {
            (user_id, event_id): (pk, email or user_email)
            for pk, user_id, event_id, email, user_email in SpeakerProfile.objects.filter(
                user_id__in=wanted_users, event_id__in=wanted_events
            ).values_list("pk", "user_id", "event_id", "email", "user__email")
        }
        for entry in batch:
            pairs = entry.data.pop("to_users", None) or []
            speakers = [list(pair) for pair in entry.data.get("to_speakers") or []]
            raw = list(entry.data.get("to") or [])
            for pair in pairs:
                user_id, email = pair[0], pair[1]
                resolved = profiles.get((user_id, entry.event_id))
                if resolved:
                    if list(resolved) not in speakers:
                        speakers.append(list(resolved))
                elif email and email not in raw:
                    raw.append(email)
            entry.data["to_speakers"] = speakers
            if raw:
                entry.data["to"] = raw
        ActivityLog.objects.bulk_update(batch, ["data"])


def mail_logs_speakers_to_users(apps, schema_editor):
    # See mail/0018's reverse
    ActivityLog = apps.get_model("common", "ActivityLog")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    queryset = ActivityLog.objects.filter(
        action_type="pretalx.mail.sent", data__has_key="to_speakers"
    ).order_by("pk")
    last_pk = 0
    while batch := list(queryset.filter(pk__gt=last_pk)[:BATCH_SIZE]):
        last_pk = batch[-1].pk
        wanted = {
            pair[0] for entry in batch for pair in (entry.data.get("to_speakers") or [])
        }
        users = dict(
            SpeakerProfile.objects.filter(
                pk__in=wanted, user__isnull=False
            ).values_list("pk", "user_id")
        )
        for entry in batch:
            speakers = []
            to_users = [list(pair) for pair in entry.data.get("to_users") or []]
            for pair in entry.data.get("to_speakers") or []:
                if user_id := users.get(pair[0]):
                    to_users.append([user_id, pair[1]])
                else:
                    speakers.append(list(pair))
            entry.data["to_speakers"] = speakers
            if to_users:
                entry.data["to_users"] = to_users
        ActivityLog.objects.bulk_update(batch, ["data"])


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0010_remove_activitylog_legacy_data"),
        ("person", "0046_speakerprofile_guid_backfill"),
    ]

    operations = [
        migrations.RunPython(account_email_to_user_email, user_email_to_account_email),
        migrations.RunPython(mail_logs_users_to_speakers, mail_logs_speakers_to_users),
    ]
