# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import random

import pytest

from pretalx.common.ui import generate_contrast_color
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


def test_track_form_init_prefills_color_for_new_track():
    event = EventFactory()

    random.seed(0)
    form = TrackForm(event=event, locales=event.locales)
    random.seed(0)
    expected = generate_contrast_color(existing_colors=[])

    assert form.initial["color"] == expected


def test_track_form_init_prefills_color_avoiding_existing_tracks():
    event = EventFactory()
    TrackFactory(event=event, color="#ff0000")
    TrackFactory(event=event, color="#00ff00")

    random.seed(0)
    form = TrackForm(event=event, locales=event.locales)
    random.seed(0)
    expected = generate_contrast_color(existing_colors=["#ff0000", "#00ff00"])

    assert form.initial["color"] == expected


def test_track_form_init_keeps_explicit_initial_color():
    event = EventFactory()

    form = TrackForm(event=event, locales=event.locales, initial={"color": "#abcdef"})

    assert form.initial["color"] == "#abcdef"


def test_track_form_init_does_not_prefill_color_when_editing():
    event = EventFactory()
    track = TrackFactory(event=event, color="#123456")

    form = TrackForm(instance=track, event=event, locales=event.locales)

    assert form.initial["color"] == "#123456"


def test_track_form_init_does_not_prefill_color_for_bound_form():
    event = EventFactory()

    form = TrackForm(data={"name_0": "Security"}, event=event, locales=event.locales)

    assert "color" not in form.initial
