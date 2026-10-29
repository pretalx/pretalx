# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.interfaces.forms import WidgetGenerationForm, WidgetSettingsForm
from tests.factories import EventFactory, RoomFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("data", "expected"),
    (({"show_widget_if_not_public": True}, True), ({}, False)),
    ids=["checked", "unchecked"],
)
def test_widgetsettingsform_valid(data, expected):
    form = WidgetSettingsForm(data=data, obj=EventFactory())

    assert form.is_valid(), form.errors
    assert form.cleaned_data == {"show_widget_if_not_public": expected}


def test_widgetgenerationform_init_sets_day_choices_and_visible_rooms():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    RoomFactory(event=event, hidden=True)
    RoomFactory()

    form = WidgetGenerationForm(instance=event)

    assert [choice[0] for choice in form.fields["days"].choices] == [
        dt.date(2024, 6, 10),
        dt.date(2024, 6, 11),
        dt.date(2024, 6, 12),
    ]
    assert list(form.fields["rooms"].queryset) == [room1, room2]
