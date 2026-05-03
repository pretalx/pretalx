# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import Min
from django.utils.timezone import now


def _collect_earliest_log_timestamps(activity_log_model, user_ct):
    """Return ``{user_pk: earliest_timestamp}`` across both log relations.

    The minimum across the two relations is taken, so a user with both an
    earlier actor-side entry and a later target-side entry gets the earlier one.
    """
    earliest = {}

    if user_ct is not None:
        for row in (
            activity_log_model.objects.filter(content_type=user_ct)
            .values("object_id")
            .annotate(m=Min("timestamp"))
        ):
            earliest[row["object_id"]] = row["m"]

    for row in (
        activity_log_model.objects.filter(person__isnull=False)
        .values("person")
        .annotate(m=Min("timestamp"))
    ):
        pk = row["person"]
        ts = row["m"]
        existing = earliest.get(pk)
        if existing is None or ts < existing:
            earliest[pk] = ts

    return earliest


def backfill_user_created(apps, schema_editor):
    User = apps.get_model("person", "User")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ActivityLog = apps.get_model("common", "ActivityLog")
    # A fresh database may not have any ContentType rows yet. The actor-side
    # lookup (person=user) doesn't need the content type, so we only skip the
    # target-side half when it's missing.
    user_ct = ContentType.objects.filter(app_label="person", model="user").first()

    earliest = _collect_earliest_log_timestamps(ActivityLog, user_ct)

    # 0037 stamped every existing row with the migration-start timestamp via
    # the DB default; we overwrite that with the earliest log timestamp where
    # we have one, and leave it otherwise.
    fallback = now()
    batch = []
    for user in User.objects.only("pk").iterator():
        user.created = earliest.get(user.pk, fallback)
        batch.append(user)
        if len(batch) >= 1000:
            User.objects.bulk_update(batch, ["created"])
            batch.clear()
    if batch:
        User.objects.bulk_update(batch, ["created"])


class Migration(migrations.Migration):
    # Run outside a single transaction so the long-running aggregation and
    # per-user updates don't hold the AccessExclusiveLock that 0037's
    # AddField briefly took. Each bulk_update commits independently.
    atomic = False

    dependencies = [
        ("person", "0037_user_created"),
        ("common", "0010_remove_activitylog_legacy_data"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(backfill_user_created, migrations.RunPython.noop)
    ]
