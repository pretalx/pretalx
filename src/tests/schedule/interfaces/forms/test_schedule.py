# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scope

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.interfaces.forms import ScheduleReleaseForm
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_schedule_release_form_init_sets_version_required():
    event = EventFactory()
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(event=event, instance=schedule)

    assert form.fields["version"].required is True


def test_schedule_release_form_init_sets_comment_rows():
    event = EventFactory()
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(event=event, instance=schedule)

    assert form.fields["comment"].widget.attrs["rows"] == 4


def test_schedule_release_form_init_notify_speakers_help_text_contains_link():
    event = EventFactory()
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(event=event, instance=schedule)

    help_text = str(form.fields["notify_speakers"].help_text)
    assert "<a href=" in help_text


def test_schedule_release_form_init_first_schedule_comment():
    """When there's no current schedule, the comment field gets the 'first schedule' phrase."""
    event = EventFactory()
    assert event.current_schedule is None
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(event=event, instance=schedule)

    assert form.fields["comment"].initial is not None
    assert str(form.fields["comment"].initial) != ""


def test_schedule_release_form_init_subsequent_schedule_comment():
    """When there is a current schedule, the comment field gets the 'new version' phrase."""
    event = EventFactory()
    schedule = event.wip_schedule
    freeze_schedule(schedule, "v1", notify_speakers=False)
    form = ScheduleReleaseForm(event=event, instance=event.wip_schedule)

    assert form.fields["comment"].initial is not None
    assert str(form.fields["comment"].initial) != ""


def test_schedule_release_form_init_guesses_version_when_no_initial():
    event = EventFactory()
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(event=event, instance=schedule)

    assert form.fields["version"].initial == "0.1"


def test_schedule_release_form_init_guesses_version_after_release():
    event = EventFactory()
    schedule = event.wip_schedule
    freeze_schedule(schedule, "v1.3", notify_speakers=False)
    form = ScheduleReleaseForm(event=event, instance=event.wip_schedule)

    assert form.fields["version"].initial == "v1.4"


def test_schedule_release_form_clean_version_valid():
    event = EventFactory()
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(
        data={"version": "v1.0", "comment": "test", "notify_speakers": True},
        event=event,
        instance=schedule,
    )
    assert form.is_valid()

    assert form.cleaned_data["version"] == "v1.0"


def test_schedule_release_form_clean_version_rejects_duplicate():
    event = EventFactory()
    schedule = event.wip_schedule
    freeze_schedule(schedule, "v1.0", notify_speakers=False)
    form = ScheduleReleaseForm(
        data={"version": "v1.0", "comment": "test", "notify_speakers": True},
        event=event,
        instance=event.wip_schedule,
    )
    assert not form.is_valid()

    assert "version" in form.errors


def test_schedule_release_form_clean_version_rejects_duplicate_case_insensitive():
    event = EventFactory()
    schedule = event.wip_schedule
    freeze_schedule(schedule, "V1.0", notify_speakers=False)
    form = ScheduleReleaseForm(
        data={"version": "v1.0", "comment": "test", "notify_speakers": True},
        event=event,
        instance=event.wip_schedule,
    )
    assert not form.is_valid()

    assert "version" in form.errors


def test_schedule_release_form_version_is_required():
    event = EventFactory()
    schedule = event.wip_schedule
    form = ScheduleReleaseForm(
        data={"version": "", "comment": "test", "notify_speakers": True},
        event=event,
        instance=schedule,
    )
    assert not form.is_valid()

    assert "version" in form.errors


def test_schedule_release_form_init_preserves_version_initial():
    """When version.initial is already set, guess_schedule_version is not called."""
    event = EventFactory()
    schedule = event.wip_schedule
    schedule.version = "custom"
    form = ScheduleReleaseForm(
        event=event, instance=schedule, initial={"version": "custom"}
    )

    assert form.fields["version"].initial == "custom"


def _expand_capacity_setup(room_capacity, session_capacity):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = True
    sub_type.save()
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        submission_type=sub_type,
        attendee_signup_capacity=session_capacity,
    )
    start = event.datetime_from
    with scope(event=event):
        TalkSlotFactory(
            submission=submission,
            schedule=event.wip_schedule,
            room=room,
            start=start,
            end=start + dt.timedelta(hours=1),
            is_visible=True,
        )
        warnings = event.wip_schedule.warnings
    return event, submission, warnings


def test_schedule_release_form_expand_capacity_fields_from_warnings():
    event, submission, warnings = _expand_capacity_setup(
        room_capacity=120, session_capacity=20
    )

    form = ScheduleReleaseForm(
        event=event, instance=event.wip_schedule, warnings=warnings
    )

    field_name = f"expand_capacity_{submission.pk}"
    assert field_name in form.fields
    assert form.fields[field_name].initial is False
    bound = form.get_expand_capacity_fields()
    assert len(bound) == 1
    assert bound[0]["submission"] == submission
    assert bound[0]["bound_field"].name == field_name


@pytest.mark.parametrize(
    ("checkbox_value", "expected_capacity"),
    (
        ("on", 300),  # checked: capacity rises to room capacity
        (None, 50),  # unchecked: capacity stays put
    ),
)
def test_schedule_release_form_apply_expand_capacity(checkbox_value, expected_capacity):
    event, submission, warnings = _expand_capacity_setup(
        room_capacity=300, session_capacity=50
    )
    data = {"version": "v1.0", "comment": "release", "notify_speakers": True}
    if checkbox_value is not None:
        data[f"expand_capacity_{submission.pk}"] = checkbox_value

    form = ScheduleReleaseForm(
        data=data, event=event, instance=event.wip_schedule, warnings=warnings
    )
    assert form.is_valid(), form.errors

    with scope(event=event):
        form.apply_expand_capacity()
        refreshed = Submission.objects.get(pk=submission.pk)
    assert refreshed.attendee_signup_capacity == expected_capacity
