# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest import mock

import pytest
from django.core.management import call_command

from pretalx.common.signals import periodic_task

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@mock.patch("pretalx.common.update_check.urllib3.request")
def test_runperiodic_sends_periodic_task_signal(mock_request):
    # patching out network so that we don't send real actual update checks
    received = []

    def handler(sender, **kwargs):
        received.append(True)

    periodic_task.connect(handler)
    try:
        call_command("runperiodic")
    finally:
        periodic_task.disconnect(handler)

    assert len(received) == 1
