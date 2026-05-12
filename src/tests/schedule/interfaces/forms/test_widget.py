# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.interfaces.forms import WidgetGenerationForm, WidgetSettingsForm
from tests.factories import EventFactory, RoomFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_widgetsettingsform_valid():
    event = EventFactory()
    data = {"show_widget_if_not_public": True}
    form = WidgetSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


def test_widgetsettingsform_unchecked():
    event = EventFactory()
    data = {}
    form = WidgetSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


def test_widgetgenerationform_init_sets_day_choices():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    form = WidgetGenerationForm(instance=event)

    days = [choice[0] for choice in form.fields["days"].choices]
    assert len(days) == 3
    assert days[0] == dt.date(2024, 6, 10)
    assert days[-1] == dt.date(2024, 6, 12)


def test_widgetgenerationform_init_sets_room_queryset():
    event = EventFactory()
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    form = WidgetGenerationForm(instance=event)

    assert set(form.fields["rooms"].queryset) == {room1, room2}


def test_widgetgenerationform_init_room_queryset_excludes_other_events():
    event = EventFactory()
    RoomFactory(event=event)
    other_event = EventFactory()
    other_room = RoomFactory(event=other_event)
    form = WidgetGenerationForm(instance=event)

    assert other_room not in form.fields["rooms"].queryset


def test_widgetgenerationform_init_locale_label():
    event = EventFactory()
    form = WidgetGenerationForm(instance=event)

    assert "language" in str(form.fields["locale"].label).lower()
