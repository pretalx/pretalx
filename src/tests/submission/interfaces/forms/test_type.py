# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.submission.interfaces.forms import SubmissionTypeForm
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_type_form_valid_with_minimal_data():
    event = EventFactory()

    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "60"},
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert valid, form.errors


def test_submission_type_form_clean_name_rejects_duplicate():
    event = EventFactory()
    SubmissionTypeFactory(event=event, name="Workshop")

    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "60"},
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert not valid
    assert "name" in form.errors


def test_submission_type_form_clean_name_allows_same_instance():
    """Editing other fields of a submission type should not conflict with its own name."""
    event = EventFactory()
    stype = SubmissionTypeFactory(event=event, name="Workshop")

    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "90"},
        instance=stype,
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert valid, form.errors


def test_submission_type_form_save_updates_default_duration():
    """Changing default_duration propagates the change to submissions that
    inherit the default."""
    event = EventFactory()
    stype = SubmissionTypeFactory(event=event, name="Workshop", default_duration=30)
    SubmissionFactory(event=event, submission_type=stype, duration=None)

    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "60"},
        instance=stype,
        event=event,
        locales=event.locales,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    result.refresh_from_db()

    assert result.default_duration == 60


def test_submission_type_form_save_without_duration_change():
    """Saving with the same default_duration does not rewrite slots."""
    event = EventFactory()
    stype = SubmissionTypeFactory(event=event, name="Workshop", default_duration=60)

    form = SubmissionTypeForm(
        data={"name_0": "Renamed Workshop", "default_duration": "60"},
        instance=stype,
        event=event,
        locales=event.locales,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    result.refresh_from_db()

    assert str(result.name) == "Renamed Workshop"
    assert result.default_duration == 60


@pytest.mark.parametrize(
    ("flag_enabled", "present"),
    ((False, False), (True, True)),
    ids=("disabled", "enabled"),
)
def test_submission_type_form_attendee_signup_field_visibility(flag_enabled, present):
    event = EventFactory(feature_flags={"attendee_signup": flag_enabled})

    form = SubmissionTypeForm(event=event, locales=event.locales)

    assert ("attendee_signup_required" in form.fields) is present


@pytest.mark.parametrize(
    ("new_name", "new_required", "commit", "expect_pinned"),
    (
        ("Workshop", False, True, True),
        ("Renamed", True, True, False),
        ("Workshop", False, False, False),
    ),
    ids=(
        "cascades_on_signup_unset",
        "no_cascade_for_unrelated_change",
        "commit_false_skips_cascade",
    ),
)
def test_submission_type_form_save_signup_cascade(
    new_name, new_required, commit, expect_pinned
):
    event = EventFactory(feature_flags={"attendee_signup": True})
    stype = SubmissionTypeFactory(
        event=event, name="Workshop", default_duration=60, attendee_signup_required=True
    )
    submission = SubmissionFactory(event=event, submission_type=stype)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        form = SubmissionTypeForm(
            data={
                "name_0": new_name,
                "default_duration": "60",
                "attendee_signup_required": new_required,
            },
            instance=stype,
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
