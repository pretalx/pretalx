# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from pretalx.common.models.log import ActivityLog
from pretalx.person.models import User

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _load_migration():
    # The module name starts with a digit, so we cannot use a normal import.
    return import_module("pretalx.person.migrations.0038_user_created_backfill")


def _load_collect():
    return _load_migration()._collect_earliest_log_timestamps


def test_collect_uses_earliest_log_entry_about_user():
    collect = _load_collect()
    user = User.objects.create_user(email="target@example.com", password="x")
    ct = ContentType.objects.get(app_label="person", model="user")
    early = timezone.now() - dt.timedelta(days=365)
    later = timezone.now() - dt.timedelta(days=30)
    a = ActivityLog.objects.create(
        content_type=ct, object_id=user.pk, action_type="pretalx.user.foo"
    )
    ActivityLog.objects.filter(pk=a.pk).update(timestamp=later)
    b = ActivityLog.objects.create(
        content_type=ct, object_id=user.pk, action_type="pretalx.user.bar"
    )
    ActivityLog.objects.filter(pk=b.pk).update(timestamp=early)

    earliest = collect(ActivityLog, ct)

    assert earliest[user.pk] == early


def test_collect_uses_earliest_log_entry_by_user():
    """Log entries where the user is the actor (person=user) also count."""
    collect = _load_collect()
    user = User.objects.create_user(email="actor@example.com", password="x")
    early = timezone.now() - dt.timedelta(days=200)
    user_ct = ContentType.objects.get(app_label="person", model="user")
    # Use a non-User content type so the only match is the person= clause.
    other_ct = ContentType.objects.get(app_label="common", model="activitylog")
    entry = ActivityLog.objects.create(
        content_type=other_ct,
        object_id=999_999,
        action_type="pretalx.submission.create",
        person=user,
    )
    ActivityLog.objects.filter(pk=entry.pk).update(timestamp=early)

    earliest = collect(ActivityLog, user_ct)

    assert earliest[user.pk] == early


def test_collect_takes_minimum_across_both_sides():
    collect = _load_collect()
    user = User.objects.create_user(email="both@example.com", password="x")
    user_ct = ContentType.objects.get(app_label="person", model="user")
    other_ct = ContentType.objects.get(app_label="common", model="activitylog")
    earlier_actor = timezone.now() - dt.timedelta(days=300)
    later_target = timezone.now() - dt.timedelta(days=30)

    a = ActivityLog.objects.create(
        content_type=user_ct, object_id=user.pk, action_type="pretalx.user.foo"
    )
    ActivityLog.objects.filter(pk=a.pk).update(timestamp=later_target)
    b = ActivityLog.objects.create(
        content_type=other_ct,
        object_id=999_999,
        action_type="pretalx.submission.create",
        person=user,
    )
    ActivityLog.objects.filter(pk=b.pk).update(timestamp=earlier_actor)

    earliest = collect(ActivityLog, user_ct)

    assert earliest[user.pk] == earlier_actor


def test_collect_returns_empty_without_logs():
    collect = _load_collect()
    user_ct = ContentType.objects.get(app_label="person", model="user")
    ActivityLog.objects.all().delete()

    assert collect(ActivityLog, user_ct) == {}


def test_collect_still_reads_actor_logs_when_user_ct_missing():
    collect = _load_collect()
    user = User.objects.create_user(email="actor2@example.com", password="x")
    early = timezone.now() - dt.timedelta(days=100)
    other_ct = ContentType.objects.get(app_label="common", model="activitylog")
    entry = ActivityLog.objects.create(
        content_type=other_ct,
        object_id=999_999,
        action_type="pretalx.submission.create",
        person=user,
    )
    ActivityLog.objects.filter(pk=entry.pk).update(timestamp=early)

    earliest = collect(ActivityLog, None)

    assert earliest[user.pk] == early


def test_backfill_overwrites_auto_now_add_default_with_log_timestamp():
    """The DB default from AddField stamps every row with the migration-run
    timestamp; the backfill must replace that with the earliest log timestamp
    where one exists, otherwise the entire reconstruction is dead code."""
    backfill = _load_migration().backfill_user_created
    user_with_log = User.objects.create_user(email="logged@example.com", password="x")
    user_without_log = User.objects.create_user(email="nolog@example.com", password="x")
    ct = ContentType.objects.get(app_label="person", model="user")
    early = timezone.now() - dt.timedelta(days=500)
    entry = ActivityLog.objects.create(
        content_type=ct, object_id=user_with_log.pk, action_type="pretalx.user.foo"
    )
    ActivityLog.objects.filter(pk=entry.pk).update(timestamp=early)
    # Simulate the state after AddField ran: all users have created set to "now".
    pre_backfill = timezone.now()
    User.objects.all().update(created=pre_backfill)

    backfill(django_apps, schema_editor=None)

    user_with_log.refresh_from_db()
    user_without_log.refresh_from_db()
    assert user_with_log.created == early
    # User with no log keeps a timestamp close to migration-run; the fallback
    # path assigns now() at backfill time, which is >= pre_backfill.
    assert user_without_log.created >= pre_backfill
