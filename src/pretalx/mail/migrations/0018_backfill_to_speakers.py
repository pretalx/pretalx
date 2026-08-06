# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict

from django.db import migrations

BATCH_SIZE = 10_000


def move_users_to_speakers(apps, schema_editor):
    QueuedMail = apps.get_model("mail", "QueuedMail")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    to_users_table = QueuedMail.to_users.through
    to_speakers_table = QueuedMail.to_speakers.through

    entries = to_users_table.objects.values_list(
        "pk", "queuedmail_id", "user_id", "queuedmail__event_id", "user__email"
    ).order_by("pk")
    last_pk = 0
    while batch := list(entries.filter(pk__gt=last_pk)[:BATCH_SIZE]):
        last_pk = batch[-1][0]
        speaker_ids = {
            (user_id, event_id): speaker_id
            for speaker_id, user_id, event_id in SpeakerProfile.objects.filter(
                user_id__in={user_id for _, _, user_id, _, _ in batch},
                event_id__in={event_id for _, _, _, event_id, _ in batch if event_id},
            ).values_list("pk", "user_id", "event_id")
        }
        to_create = []
        to_delete = []
        fallback = defaultdict(list)
        for pk, mail_id, user_id, event_id, email in batch:
            if speaker_id := speaker_ids.get((user_id, event_id)):
                to_create.append(
                    to_speakers_table(
                        queuedmail_id=mail_id, speakerprofile_id=speaker_id
                    )
                )
            else:
                fallback[mail_id].append(email)
            to_delete.append(pk)
        to_speakers_table.objects.bulk_create(to_create, ignore_conflicts=True)
        if fallback:
            mails = QueuedMail.objects.only("id", "to").in_bulk(fallback.keys())
            for mail_id, emails in fallback.items():
                mail = mails[mail_id]
                addresses = [
                    address for address in (mail.to or "").split(",") if address
                ]
                addresses += [
                    email for email in emails if email and email not in addresses
                ]
                mail.to = ",".join(addresses)
            QueuedMail.objects.bulk_update(mails.values(), ["to"])
        to_users_table.objects.filter(pk__in=to_delete).delete()


def move_speakers_to_users(apps, schema_editor):
    QueuedMail = apps.get_model("mail", "QueuedMail")
    User = apps.get_model("person", "User")
    to_users_table = QueuedMail.to_users.through
    to_speakers_table = QueuedMail.to_speakers.through

    entries = (
        to_speakers_table.objects.filter(speakerprofile__user__isnull=False)
        .values_list("pk", "queuedmail_id", "speakerprofile__user_id")
        .order_by("pk")
    )
    last_pk = 0
    while batch := list(entries.filter(pk__gt=last_pk)[:BATCH_SIZE]):
        last_pk = batch[-1][0]
        to_users_table.objects.bulk_create(
            [
                to_users_table(queuedmail_id=mail_id, user_id=user_id)
                for _, mail_id, user_id in batch
            ],
            ignore_conflicts=True,
        )
        to_speakers_table.objects.filter(pk__in=[pk for pk, _, _ in batch]).delete()

    mails = (
        QueuedMail.objects.exclude(to=None)
        .exclude(to="")
        .only("id", "to")
        .order_by("pk")
    )
    last_pk = 0
    while batch := list(mails.filter(pk__gt=last_pk)[:BATCH_SIZE]):
        last_pk = batch[-1].pk
        addresses = set()
        for mail in batch:
            addresses.update(address for address in mail.to.split(",") if address)
        users = {
            email: user_id
            for user_id, email in User.objects.filter(email__in=addresses).values_list(
                "pk", "email"
            )
        }
        to_create = []
        to_update = []
        for mail in batch:
            mail_addresses = [address for address in mail.to.split(",") if address]
            kept = [address for address in mail_addresses if address not in users]
            to_create.extend(
                to_users_table(queuedmail_id=mail.pk, user_id=users[address])
                for address in mail_addresses
                if address in users
            )
            if kept != mail_addresses:
                mail.to = ",".join(kept) or None
                to_update.append(mail)
        to_users_table.objects.bulk_create(to_create, ignore_conflicts=True)
        QueuedMail.objects.bulk_update(to_update, ["to"])


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0017_queuedmail_to_speakers"),
        ("person", "0046_speakerprofile_guid_backfill"),
    ]

    operations = [migrations.RunPython(move_users_to_speakers, move_speakers_to_users)]
