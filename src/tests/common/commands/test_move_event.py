# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.management import call_command

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_move_event_handle_shifts_event_dates(event):
    old_from = event.date_from
    old_to = event.date_to
    new_date = old_from + dt.timedelta(days=5)

    call_command("move_event", event=event.slug, date=new_date.isoformat())
    event.refresh_from_db()

    assert event.date_from == new_date
    assert event.date_to == old_to + dt.timedelta(days=5)


def test_move_event_handle_shifts_talk_slot_times(talk_slot):
    event = talk_slot.submission.event
    old_start = talk_slot.start
    old_end = talk_slot.end
    new_date = event.date_from + dt.timedelta(days=3)

    call_command("move_event", event=event.slug, date=new_date.isoformat())

    talk_slot.refresh_from_db()
    assert talk_slot.start == old_start + dt.timedelta(days=3)
    assert talk_slot.end == old_end + dt.timedelta(days=3)


def test_move_event_handle_same_date_no_change(talk_slot):
    event = talk_slot.submission.event
    old_from = event.date_from
    old_to = event.date_to
    old_start = talk_slot.start

    call_command("move_event", event=event.slug, date=old_from.isoformat())
    event.refresh_from_db()

    assert event.date_from == old_from
    assert event.date_to == old_to
    talk_slot.refresh_from_db()
    assert talk_slot.start == old_start
