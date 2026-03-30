# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
import responses
from django.core.management import call_command

from pretalx.common.signals import periodic_task

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@responses.activate
def test_runperiodic_sends_periodic_task_signal():
    received = []

    def handler(sender, **kwargs):
        received.append(True)

    periodic_task.connect(handler)
    try:
        call_command("runperiodic")
    finally:
        periodic_task.disconnect(handler)

    assert len(received) == 1
