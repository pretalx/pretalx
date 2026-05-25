# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import random

import pytest
from django_scopes import scope

from pretalx.common.ui import generate_contrast_color
from pretalx.submission.interfaces.forms import TrackForm
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    SubmissionFactory,
    TrackFactory,
)

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
    event = EventFactory()
    track = TrackFactory(event=event)

    form = TrackForm(instance=track, event=event, locales=event.locales)

    assert str(track.pk) in form.fields["requires_access_code"].help_text


def test_track_form_init_no_access_code_link_for_new_track():
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


@pytest.mark.parametrize(
    ("flag_enabled", "present"),
    ((False, False), (True, True)),
    ids=("disabled", "enabled"),
)
def test_track_form_attendee_signup_field_visibility(flag_enabled, present):
    event = EventFactory(feature_flags={"attendee_signup": flag_enabled})

    form = TrackForm(event=event, locales=event.locales)

    assert ("attendee_signup_required" in form.fields) is present


@pytest.mark.parametrize(
    ("new_name", "new_required", "commit", "expect_pinned"),
    (
        ("With signup", False, True, True),
        ("Renamed", True, True, False),
        ("With signup", False, False, False),
    ),
    ids=(
        "cascades_on_signup_unset",
        "no_cascade_for_unrelated_change",
        "commit_false_skips_cascade",
    ),
)
def test_track_form_save_signup_cascade(new_name, new_required, commit, expect_pinned):
    event = EventFactory(feature_flags={"attendee_signup": True})
    track = TrackFactory(event=event, name="With signup", attendee_signup_required=True)
    submission = SubmissionFactory(event=event, track=track)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        form = TrackForm(
            data={
                "name_0": new_name,
                "color": track.color,
                "attendee_signup_required": new_required,
            },
            instance=track,
            event=event,
            locales=event.locales,
        )
        assert form.is_valid(), form.errors
        form.save(commit=commit)

        submission.refresh_from_db()
    if expect_pinned:
        assert form.signup_pinned_submissions == [submission]
        assert submission.attendee_signup_required is True
    else:
        assert form.signup_pinned_submissions == []
        assert submission.attendee_signup_required is None
