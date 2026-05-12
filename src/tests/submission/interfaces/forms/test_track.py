# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.submission.interfaces.forms import TrackForm
from tests.factories import EventFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_track_form_valid_with_minimal_data():
    event = EventFactory()

    form = TrackForm(
        data={"name_0": "Security", "color": "#ff0000"},
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert valid, form.errors


def test_track_form_clean_name_rejects_duplicate():
    event = EventFactory()
    TrackFactory(event=event, name="Security")

    form = TrackForm(
        data={"name_0": "Security", "color": "#00ff00"},
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert not valid
    assert "name" in form.errors


def test_track_form_clean_name_allows_same_instance():
    event = EventFactory()
    track = TrackFactory(event=event, name="Security")

    form = TrackForm(
        data={"name_0": "Security", "color": "#ff0000"},
        instance=track,
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert valid, form.errors


def test_track_form_init_adds_access_code_link_for_existing_track():
    """Existing tracks get a help text link to create access codes."""
    event = EventFactory()
    track = TrackFactory(event=event)

    form = TrackForm(instance=track, event=event, locales=event.locales)

    assert str(track.pk) in form.fields["requires_access_code"].help_text


def test_track_form_init_no_access_code_link_for_new_track():
    """New tracks (no pk) don't get the access code creation link."""
    event = EventFactory()

    form = TrackForm(event=event, locales=event.locales)

    assert "<a href=" not in str(form.fields["requires_access_code"].help_text)
