# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scope

from pretalx.common.text.phrases import phrases
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
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


def test_schedule_release_form_init_before_first_release():
    event = EventFactory()
    template_url = mail_template_by_role(
        event, MailTemplateRoles.NEW_SCHEDULE
    ).urls.base

    form = ScheduleReleaseForm(event=event, instance=event.wip_schedule)
    custom = ScheduleReleaseForm(
        event=event, instance=event.wip_schedule, initial={"version": "custom"}
    )

    assert form.fields["notify_speakers"].help_text == (
        f"<a href='{template_url}'>Email template</a>"
    )
    assert form.fields["comment"].initial == phrases.schedule.first_schedule
    assert form.fields["version"].initial == "0.1"
    assert custom.fields["version"].initial == "custom"


def test_schedule_release_form_init_after_release():
    event = EventFactory()
    freeze_schedule(event.wip_schedule, "v1.3", notify_speakers=False)

    form = ScheduleReleaseForm(event=event, instance=event.wip_schedule)

    assert form.fields["comment"].initial == "We released a new schedule version!"
    assert form.fields["version"].initial == "v1.4"


@pytest.mark.parametrize(
    ("version", "errors"),
    (
        ("v2.0", {}),
        (
            "v1.0",
            {
                "version": [
                    "This schedule version was used already, please choose a different one."
                ]
            },
        ),
        (
            "200 km/h",
            {
                "version": [
                    "Schedule versions cannot contain slashes or be “.” or “..”."
                ]
            },
        ),
        ("", {"version": ["This field is required."]}),
    ),
    ids=["valid", "duplicate_case_insensitive", "slash", "required"],
)
def test_schedule_release_form_clean_version(version, errors):
    event = EventFactory()
    freeze_schedule(event.wip_schedule, "V1.0", notify_speakers=False)

    form = ScheduleReleaseForm(
        data={"version": version, "comment": "test", "notify_speakers": True},
        event=event,
        instance=event.wip_schedule,
    )

    assert form.is_valid() == (not errors)
    assert form.errors == errors
    assert form.cleaned_data.get("version") == (version if not errors else None)


@pytest.mark.parametrize(
    ("checkbox_value", "expected_capacity"),
    (
        ("on", 300),  # checked: capacity rises to room capacity
        (None, 50),  # unchecked: capacity stays put
    ),
)
def test_schedule_release_form_apply_expand_capacity(checkbox_value, expected_capacity):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = True
    sub_type.save()
    room = RoomFactory(event=event, capacity=300)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        submission_type=sub_type,
        attendee_signup_capacity=50,
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
    field_name = f"expand_capacity_{submission.pk}"
    data = {"version": "v1.0", "comment": "release", "notify_speakers": True}
    if checkbox_value is not None:
        data[field_name] = checkbox_value

    form = ScheduleReleaseForm(
        data=data, event=event, instance=event.wip_schedule, warnings=warnings
    )
    assert form.is_valid(), form.errors
    bound = form.get_expand_capacity_fields()
    with scope(event=event):
        form.apply_expand_capacity()
        refreshed = Submission.objects.get(pk=submission.pk)

    assert form.fields[field_name].initial is False
    assert [(entry["submission"], entry["bound_field"].name) for entry in bound] == [
        (submission, field_name)
    ]
    assert refreshed.attendee_signup_capacity == expected_capacity
