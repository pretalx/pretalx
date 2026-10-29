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
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_type_form_validates_name_and_propagates_duration():
    event = EventFactory(feature_flags={"attendee_signup": False})

    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "30"},
        event=event,
        locales=event.locales,
    )
    assert "attendee_signup_required" not in form.fields
    assert form.is_valid(), form.errors
    stype = form.save()
    assert form.signup_pinned_submissions == []

    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "60"},
        event=event,
        locales=event.locales,
    )

    assert not form.is_valid()
    assert list(form.errors) == ["name"]

    submission = SubmissionFactory(event=event, submission_type=stype, duration=None)
    slot = TalkSlotFactory(submission=submission)
    form = SubmissionTypeForm(
        data={"name_0": "Workshop", "default_duration": "60"},
        instance=stype,
        event=event,
        locales=event.locales,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    result.refresh_from_db()
    slot.refresh_from_db(fields=["end"])
    assert result.default_duration == 60
    assert (slot.end - slot.start).total_seconds() == 3600

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

    event = EventFactory(feature_flags={"attendee_signup": True})
    form = SubmissionTypeForm(event=event, locales=event.locales)

    assert "attendee_signup_required" in form.fields


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
    assert form.signup_pinned_submissions == ([submission] if expect_pinned else [])
    assert submission.attendee_signup_required is (True if expect_pinned else None)
