# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from unittest.mock import patch

import pytest
from django.core.management import call_command

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_move_event_command_parses_iso_date(event):
    """The management command parses --date and delegates to the domain
    function with that date."""
    target = event.date_from + dt.timedelta(days=5)
    with patch(
        "pretalx.common.management.commands.move_event.move_full_event"
    ) as mock_move:
        call_command("move_event", event=event.slug, date=target.isoformat())

    mock_move.assert_called_once()
    args, _kwargs = mock_move.call_args
    assert args[0].pk == event.pk
    assert args[1] == target


def test_move_event_command_defaults_to_today(event):
    """Without --date, the command shifts to today."""
    today = dt.date(2024, 1, 1)
    fake_now = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.UTC)
    with (
        patch(
            "pretalx.common.management.commands.move_event.now", return_value=fake_now
        ),
        patch(
            "pretalx.common.management.commands.move_event.move_full_event"
        ) as mock_move,
    ):
        call_command("move_event", event=event.slug)

    args, _kwargs = mock_move.call_args
    assert args[1] == today
