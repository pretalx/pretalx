# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.schedule.domain.ical import get_slot_ical, serialize_calendar
from pretalx.schedule.interfaces.responses import CalendarResponse
from tests.factories import TalkSlotFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_calendar_response_serves_ics_attachment():
    slot = TalkSlotFactory()
    cal = get_slot_ical(slot)

    response = CalendarResponse(cal, "myevent-CODE")

    assert response["Content-Type"] == "text/calendar"
    assert response["Content-Disposition"] == 'attachment; filename="myevent-CODE.ics"'
    assert response.content.decode() == serialize_calendar(cal)


@pytest.mark.django_db
def test_calendar_response_sanitizes_filename():
    slot = TalkSlotFactory()

    response = CalendarResponse(get_slot_ical(slot), "münich-café")

    assert response["Content-Disposition"] == 'attachment; filename="munich-cafe.ics"'
