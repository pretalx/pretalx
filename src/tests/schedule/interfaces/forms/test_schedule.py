# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.interfaces.forms import ScheduleReleaseForm
from tests.factories import EventFactory

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
