# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest

from pretalx.orga.forms.schedule import ScheduleExportForm, ScheduleReleaseForm
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
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
    schedule.freeze("v1", notify_speakers=False)
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
    schedule.freeze("v1.3", notify_speakers=False)
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
    schedule.freeze("v1.0", notify_speakers=False)
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
    schedule.freeze("V1.0", notify_speakers=False)
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


def test_schedule_export_form_target_choices_exclude_draft():
    event = EventFactory()
    form = ScheduleExportForm(event=event)

    target_values = [choice[0] for choice in form.fields["target"].choices]
    expected = ["all"] + [
        state
        for state, _ in SubmissionStates.choices
        if state != SubmissionStates.DRAFT
    ]
    assert target_values == expected


def test_schedule_export_form_has_extra_fields():
    event = EventFactory()
    form = ScheduleExportForm(event=event)

    for field_name in (
        "speaker_ids",
        "speaker_names",
        "room",
        "start",
        "start_date",
        "start_time",
        "end",
        "end_date",
        "end_time",
        "median_score",
        "mean_score",
        "resources",
    ):
        assert field_name in form.fields, f"Missing field: {field_name}"


def test_schedule_export_form_has_model_fields():
    event = EventFactory()
    form = ScheduleExportForm(event=event)

    for field_name in ScheduleExportForm.Meta.model_fields:
        assert field_name in form.fields, f"Missing model field: {field_name}"


def test_schedule_export_form_questions_property():
    event = EventFactory()
    sub_q = QuestionFactory(event=event, target="submission")
    QuestionFactory(event=event, target="speaker")
    form = ScheduleExportForm(event=event)

    assert list(form.questions) == [sub_q]


def test_schedule_export_form_question_fields_added():
    event = EventFactory()
    question = QuestionFactory(event=event, target="submission")
    form = ScheduleExportForm(event=event)

    assert f"question_{question.pk}" in form.fields


def test_schedule_export_form_filename():
    event = EventFactory()
    form = ScheduleExportForm(event=event)

    assert form.filename == f"{event.slug}_sessions"


def test_schedule_export_form_export_field_names():
    event = EventFactory()
    form = ScheduleExportForm(event=event)

    assert form.export_field_names == [
        *ScheduleExportForm.Meta.model_fields,
        "speaker_ids",
        "speaker_names",
        "room",
        "start",
        "start_date",
        "start_time",
        "end",
        "end_date",
        "end_time",
        "median_score",
        "mean_score",
        "resources",
    ]


def test_schedule_export_form_get_queryset_all():
    event = EventFactory()
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    form = ScheduleExportForm(
        data={"export_format": "json", "target": ["all"], "title": True}, event=event
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert set(qs) == {sub1, sub2}


def test_schedule_export_form_get_queryset_filtered():
    event = EventFactory()
    sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    form = ScheduleExportForm(
        data={
            "export_format": "json",
            "target": [SubmissionStates.ACCEPTED],
            "title": True,
        },
        event=event,
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert qs == [sub_accepted]


def test_schedule_export_form_get_speaker_ids_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    form = ScheduleExportForm(event=event)
    result = form._get_speaker_ids_value(sub)

    assert result == [speaker.code]


def test_schedule_export_form_get_speaker_names_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    form = ScheduleExportForm(event=event)
    result = form._get_speaker_names_value(sub)

    assert result == [speaker.get_display_name()]


def test_schedule_export_form_get_room_value_with_slot():
    event = EventFactory()
    room = RoomFactory(event=event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    TalkSlotFactory(submission=sub, schedule=wip, room=room)
    wip.freeze("v1", notify_speakers=False)
    sub = type(sub).objects.get(pk=sub.pk)
    form = ScheduleExportForm(event=event)
    result = form._get_room_value(sub)

    assert str(result) == str(room.name)


@pytest.mark.parametrize(
    "method_name",
    (
        "_get_room_value",
        "_get_start_value",
        "_get_start_date_value",
        "_get_start_time_value",
        "_get_end_value",
        "_get_end_date_value",
        "_get_end_time_value",
    ),
)
def test_schedule_export_form_getter_returns_none_without_slot(method_name):
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = getattr(form, method_name)(sub)

    assert result is None


def test_schedule_export_form_get_start_with_slot():
    event = EventFactory()
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    slot = TalkSlotFactory(submission=sub, schedule=wip)
    wip.freeze("v1", notify_speakers=False)
    sub = type(sub).objects.get(pk=sub.pk)
    form = ScheduleExportForm(event=event)

    start_val = form._get_start_value(sub)
    start_date_val = form._get_start_date_value(sub)
    start_time_val = form._get_start_time_value(sub)

    local_start = slot.start.astimezone(event.tz)
    assert start_val == local_start.isoformat()
    assert start_date_val == local_start.date().isoformat()
    assert start_time_val == local_start.time().isoformat()


def test_schedule_export_form_get_end_with_slot():
    event = EventFactory()
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    slot = TalkSlotFactory(submission=sub, schedule=wip)
    wip.freeze("v1", notify_speakers=False)
    sub = type(sub).objects.get(pk=sub.pk)
    form = ScheduleExportForm(event=event)

    end_val = form._get_end_value(sub)
    end_date_val = form._get_end_date_value(sub)
    end_time_val = form._get_end_time_value(sub)

    local_end = slot.end.astimezone(event.tz)
    assert end_val == local_end.isoformat()
    assert end_date_val == local_end.date().isoformat()
    assert end_time_val == local_end.time().isoformat()


def test_schedule_export_form_get_duration_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event, duration=45)
    form = ScheduleExportForm(event=event)
    result = form._get_duration_value(sub)

    assert result == 45


def test_schedule_export_form_get_image_value_no_image():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form._get_image_value(sub)

    assert result == ""


def test_schedule_export_form_get_created_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form._get_created_value(sub)

    assert result == sub.created.isoformat()


def test_schedule_export_form_get_submission_type_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form._get_submission_type_value(sub)

    assert str(result) == str(sub.submission_type.name)


def test_schedule_export_form_get_track_value():
    event = EventFactory()
    track = TrackFactory(event=event)
    sub = SubmissionFactory(event=event, track=track)
    form = ScheduleExportForm(event=event)
    result = form._get_track_value(sub)

    assert str(result) == str(track.name)


def test_schedule_export_form_get_track_value_none():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form._get_track_value(sub)

    assert result is None


def test_schedule_export_form_get_tags_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    tag = TagFactory(event=event)
    sub.tags.add(tag)
    form = ScheduleExportForm(event=event)
    result = form._get_tags_value(sub)

    assert result == [tag.tag]


def test_schedule_export_form_get_tags_value_empty():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form._get_tags_value(sub)

    assert result is None


def test_schedule_export_form_get_resources_value():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    resource = ResourceFactory(submission=sub, is_public=True)
    form = ScheduleExportForm(event=event)
    result = form._get_resources_value(sub)

    assert result == [resource.url]


def test_schedule_export_form_get_resources_value_empty():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form._get_resources_value(sub)

    assert result == []


def test_schedule_export_form_get_answer():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target="submission")
    answer = AnswerFactory(question=question, submission=sub)
    form = ScheduleExportForm(event=event)
    result = form.get_answer(question, sub)

    assert result == answer


def test_schedule_export_form_get_answer_none():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target="submission")
    form = ScheduleExportForm(event=event)
    result = form.get_answer(question, sub)

    assert result is None


def test_schedule_release_form_init_preserves_version_initial():
    """When version.initial is already set, guess_schedule_version is not called."""
    event = EventFactory()
    schedule = event.wip_schedule
    schedule.version = "custom"
    form = ScheduleReleaseForm(
        event=event, instance=schedule, initial={"version": "custom"}
    )

    assert form.fields["version"].initial == "custom"


def test_schedule_export_form_question_field_names():
    event = EventFactory()
    q = QuestionFactory(event=event, target="submission")
    form = ScheduleExportForm(event=event)

    assert form.question_field_names == [f"question_{q.pk}"]


def test_schedule_export_form_export_fields():
    event = EventFactory()
    form = ScheduleExportForm(event=event)

    field_names = [bf.name for bf in form.export_fields]
    assert "title" in field_names
    assert "speaker_ids" in field_names


def test_schedule_export_form_clean_csv_without_delimiter():
    event = EventFactory()
    form = ScheduleExportForm(
        event=event, data={"export_format": "csv", "target": ["all"], "title": True}
    )

    assert not form.is_valid()
    assert "data_delimiter" in form.errors


def test_schedule_export_form_clean_json_without_delimiter():
    event = EventFactory()
    form = ScheduleExportForm(
        event=event, data={"export_format": "json", "target": ["all"], "title": True}
    )

    assert form.is_valid(), form.errors


def test_schedule_export_form_get_object_attribute_custom_method():
    """get_object_attribute uses _get_<attr>_value if it exists."""
    event = EventFactory()
    sub = SubmissionFactory(event=event, duration=45)
    form = ScheduleExportForm(event=event)
    result = form.get_object_attribute(sub, "duration")

    assert result == 45


def test_schedule_export_form_get_object_attribute_direct():
    """get_object_attribute falls back to direct attribute access."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form.get_object_attribute(sub, "code")

    assert result == sub.code


def test_schedule_export_form_get_object_attribute_missing():
    """get_object_attribute returns None for missing attributes."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event)
    result = form.get_object_attribute(sub, "nonexistent_field")

    assert result is None


def test_schedule_export_form_get_data():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(
        event=event, data={"export_format": "json", "target": ["all"], "title": True}
    )
    form.is_valid()
    data = form.get_data(form.get_queryset(), ["title"], [])

    assert len(data) == 1
    assert data[0]["ID"] == sub.code
    assert str(sub.title) in str(data[0].values())


def test_schedule_export_form_get_data_with_questions():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target="submission")
    answer = AnswerFactory(question=question, submission=sub)
    form = ScheduleExportForm(event=event)
    data = form.get_data(form.event.submissions.all(), [], [question])

    assert len(data) == 1
    assert data[0][str(question.question)] == answer.answer_string


def test_schedule_export_form_get_data_without_answer():
    event = EventFactory()
    SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target="submission")
    form = ScheduleExportForm(event=event)
    data = form.get_data(form.event.submissions.all(), [], [question])

    assert data[0][str(question.question)] is None


def test_schedule_export_form_export_data_returns_none_when_empty():
    """export_data returns None when no data matches."""
    event = EventFactory()
    form = ScheduleExportForm(
        event=event,
        data={
            "export_format": "json",
            "target": [SubmissionStates.ACCEPTED],
            "title": True,
        },
    )
    form.is_valid()
    result = form.export_data()

    assert result is None


def test_schedule_export_form_export_data_json():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(
        event=event, data={"export_format": "json", "target": ["all"], "title": True}
    )
    form.is_valid()
    response = form.export_data()

    assert response["Content-Type"] == "application/json; charset=utf-8"
    assert f"{event.slug}_sessions.json" in response["Content-Disposition"]
    data = json.loads(response.content)
    assert len(data) == 1
    assert data[0]["ID"] == sub.code


def test_schedule_export_form_export_data_csv():
    event = EventFactory()
    SubmissionFactory(event=event)
    form = ScheduleExportForm(
        event=event,
        data={
            "export_format": "csv",
            "data_delimiter": "newline",
            "target": ["all"],
            "title": True,
        },
    )
    form.is_valid()
    response = form.export_data()

    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert f"{event.slug}_sessions.csv" in response["Content-Disposition"]
    content = response.content.decode()
    assert "ID" in content


def test_schedule_export_form_csv_export_joins_lists_with_delimiter():
    """csv_export joins list values using the chosen delimiter."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    sub.speakers.add(speaker1, speaker2)
    form = ScheduleExportForm(
        event=event,
        data={
            "export_format": "csv",
            "data_delimiter": "comma",
            "target": ["all"],
            "speaker_names": True,
        },
    )
    form.is_valid()
    response = form.export_data()

    content = response.content.decode()
    assert ", " in content


def test_schedule_export_form_export_data_with_question():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target="submission")
    answer = AnswerFactory(question=question, submission=sub)
    form = ScheduleExportForm(
        event=event,
        data={
            "export_format": "json",
            "target": ["all"],
            f"question_{question.pk}": True,
        },
    )
    form.is_valid()
    response = form.export_data()

    data = json.loads(response.content)
    assert data[0][str(question.question)] == answer.answer_string
