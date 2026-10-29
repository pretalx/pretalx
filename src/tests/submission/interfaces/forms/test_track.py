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


def test_track_form_rejects_duplicate_names_except_own():
    event = EventFactory()

    form = TrackForm(
        data={"name_0": "Security", "color": "#ff0000"},
        event=event,
        locales=event.locales,
    )
    assert form.is_valid(), form.errors
    track = form.save()

    form = TrackForm(
        data={"name_0": "Security", "color": "#00ff00"},
        event=event,
        locales=event.locales,
    )

    assert not form.is_valid()
    assert list(form.errors) == ["name"]

    form = TrackForm(
        data={"name_0": "Security", "color": "#ff0000"},
        instance=track,
        event=event,
        locales=event.locales,
    )

    assert form.is_valid(), form.errors


def test_track_form_init_prefills_color_and_links_access_codes():
    event = EventFactory(feature_flags={"attendee_signup": False})

    random.seed(0)
    form = TrackForm(event=event, locales=event.locales)
    random.seed(0)

    assert form.initial["color"] == generate_contrast_color(existing_colors=[])
    assert "<a href=" not in str(form.fields["requires_access_code"].help_text)
    assert "attendee_signup_required" not in form.fields

    TrackFactory(event=event, color="#ff0000")
    track = TrackFactory(event=event, color="#00ff00")

    random.seed(0)
    form = TrackForm(event=event, locales=event.locales)
    random.seed(0)

    assert form.initial["color"] == generate_contrast_color(
        existing_colors=["#ff0000", "#00ff00"]
    )

    form = TrackForm(event=event, locales=event.locales, initial={"color": "#abcdef"})
    assert form.initial["color"] == "#abcdef"

    form = TrackForm(data={"name_0": "Security"}, event=event, locales=event.locales)
    assert "color" not in form.initial

    form = TrackForm(instance=track, event=event, locales=event.locales)

    assert form.initial["color"] == "#00ff00"
    assert str(track.pk) in form.fields["requires_access_code"].help_text

    event = EventFactory(feature_flags={"attendee_signup": True})
    form = TrackForm(event=event, locales=event.locales)

    assert "attendee_signup_required" in form.fields


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
    assert form.signup_pinned_submissions == ([submission] if expect_pinned else [])
    assert submission.attendee_signup_required is (True if expect_pinned else None)
