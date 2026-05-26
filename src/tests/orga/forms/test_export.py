# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json
from operator import attrgetter

import pytest

from pretalx.orga.forms.export import (
    ReviewExportForm,
    ScheduleExportForm,
    SpeakerExportForm,
)
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import QuestionTarget, SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_review_export_form_init():
    """ReviewExportForm creates expected fields from model_fields."""
    event = EventFactory()
    user = make_orga_user(event)

    form = ReviewExportForm(event=event, user=user)

    assert "score" in form.fields
    assert "text" in form.fields
    assert "created" in form.fields
    assert "updated" in form.fields
    assert "target" in form.fields
    assert "submission_id" in form.fields
    assert "submission_title" in form.fields
    assert "user_name" in form.fields
    assert "user_email" in form.fields
    # data_delimiter is set to None so should be removed
    assert "data_delimiter" not in form.fields


def test_review_export_form_score_categories_single():
    """With only one score category (default), score_categories returns empty."""
    event = EventFactory()
    user = make_orga_user(event)

    form = ReviewExportForm(event=event, user=user)

    assert form.score_categories == []


def test_review_export_form_score_categories_multiple():
    """With multiple active categories, score_categories returns all of them."""
    event = EventFactory()
    user = make_orga_user(event)
    cat2 = ReviewScoreCategoryFactory(event=event, active=True)

    form = ReviewExportForm(event=event, user=user)

    # Default category from build_initial_data + cat2
    assert len(form.score_categories) == 2
    assert cat2 in form.score_categories


def test_review_export_form_score_categories_excludes_inactive():
    event = EventFactory()
    user = make_orga_user(event)
    ReviewScoreCategoryFactory(event=event, active=False)

    form = ReviewExportForm(event=event, user=user)

    # Only the default one (from build_initial_data), which is active
    assert form.score_categories == []


def test_review_export_form_builds_score_fields():
    """When there are multiple score categories, score fields are created."""
    event = EventFactory()
    user = make_orga_user(event)
    default_cat = event.score_categories.first()
    cat2 = ReviewScoreCategoryFactory(event=event, active=True)

    form = ReviewExportForm(event=event, user=user)

    assert f"score_{default_cat.pk}" in form.fields
    assert f"score_{cat2.pk}" in form.fields


def test_review_export_form_filename():
    event = EventFactory()
    user = make_orga_user(event)

    form = ReviewExportForm(event=event, user=user)

    assert form.filename == f"{event.slug}_reviews"


def test_review_export_form_export_field_names():
    event = EventFactory()
    user = make_orga_user(event)

    form = ReviewExportForm(event=event, user=user)

    expected = [
        "score",
        "text",
        "submission_id",
        "submission_title",
        "created",
        "updated",
        "user_name",
        "user_email",
    ]
    assert form.export_field_names == expected


def test_review_export_form_export_field_names_with_score_categories():
    """score_field_names appear in export_field_names when multiple categories exist."""
    event = EventFactory()
    user = make_orga_user(event)
    cat2 = ReviewScoreCategoryFactory(event=event, active=True)

    form = ReviewExportForm(event=event, user=user)

    assert f"score_{cat2.pk}" in form.export_field_names


@pytest.mark.parametrize(
    ("method", "attr_path"),
    (
        ("_get_submission_id_value", "submission.code"),
        ("_get_submission_title_value", "submission.title"),
        ("_get_user_name_value", "user.name"),
        ("_get_user_email_value", "user.email"),
    ),
)
def test_review_export_form_value_getter(method, attr_path):
    event = EventFactory()
    user = make_orga_user(event)
    review = ReviewFactory(submission__event=event)

    form = ReviewExportForm(event=event, user=user)

    assert getattr(form, method)(review) == attrgetter(attr_path)(review)


def test_review_export_form_get_additional_data():
    """get_additional_data returns score values keyed by category name."""
    event = EventFactory()
    user = make_orga_user(event)
    cat2 = ReviewScoreCategoryFactory(event=event, active=True)
    score = ReviewScoreFactory(category=cat2, value=5)
    review = ReviewFactory(submission__event=event)
    review.scores.add(score)

    form = ReviewExportForm(event=event, user=user)

    data = form.get_additional_data(review)

    assert str(cat2.name) in data
    assert data[str(cat2.name)] == score.value


def test_review_export_form_get_additional_data_no_score():
    """get_additional_data returns None for categories without a score."""
    event = EventFactory()
    user = make_orga_user(event)
    cat2 = ReviewScoreCategoryFactory(event=event, active=True)
    review = ReviewFactory(submission__event=event)

    form = ReviewExportForm(event=event, user=user)
    data = form.get_additional_data(review)

    assert data[str(cat2.name)] is None


@pytest.mark.parametrize(
    ("target", "expected_states"),
    (
        ("all", None),
        ("accepted", {SubmissionStates.ACCEPTED}),
        ("confirmed", {SubmissionStates.CONFIRMED}),
        ("rejected", {SubmissionStates.REJECTED}),
    ),
)
def test_review_export_form_get_queryset_filters_by_target(target, expected_states):
    event = EventFactory()
    user = make_orga_user(event)
    sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    sub_rejected = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    review_accepted = ReviewFactory(submission=sub_accepted)
    review_rejected = ReviewFactory(submission=sub_rejected)

    form = ReviewExportForm(
        event=event, user=user, data={"export_format": "json", "target": target}
    )
    assert form.is_valid(), form.errors
    queryset = form.get_queryset()

    expected = set()
    for review, state in [
        (review_accepted, SubmissionStates.ACCEPTED),
        (review_rejected, SubmissionStates.REJECTED),
    ]:
        if expected_states is None or state in expected_states:
            expected.add(review)
    assert set(queryset) == expected


def test_review_export_form_get_queryset_excludes_own_submissions():
    """get_queryset excludes reviews on submissions by the requesting user."""
    event = EventFactory()
    user = make_orga_user(event)
    speaker = SpeakerFactory(event=event, user=user)
    own_sub = SubmissionFactory(event=event)
    own_sub.speakers.add(speaker)
    other_sub = SubmissionFactory(event=event)
    ReviewFactory(submission=own_sub)  # should be excluded
    review_other = ReviewFactory(submission=other_sub)

    form = ReviewExportForm(
        event=event, user=user, data={"export_format": "json", "target": "all"}
    )
    assert form.is_valid(), form.errors
    queryset = form.get_queryset()

    assert set(queryset) == {review_other}


@pytest.mark.parametrize("has_answer", (True, False))
def test_review_export_form_get_answer(has_answer):
    """get_answer returns the matching Answer or None."""
    event = EventFactory()
    user = make_orga_user(event)
    question = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    review = ReviewFactory(submission__event=event)
    if has_answer:
        answer = AnswerFactory(question=question, review=review, answer="42")

    form = ReviewExportForm(event=event, user=user)
    result = form.get_answer(question, review)

    if has_answer:
        assert result == answer
    else:
        assert result is None


def test_review_export_form_questions():
    """questions property returns reviewer questions accessible to the user."""
    event = EventFactory()
    user = make_orga_user(event)
    reviewer_q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True
    )
    QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, active=True)

    form = ReviewExportForm(event=event, user=user)

    assert set(form.questions) == {reviewer_q}


def test_review_export_form_export_data_json():
    """export_data produces a JSON response covering export.py code paths
    including objects without code and get_additional_data."""
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    ReviewFactory(submission=sub)
    form = ReviewExportForm(
        event=event,
        user=user,
        data={"export_format": "json", "target": "all", "score": True},
    )
    assert form.is_valid(), form.errors
    response = form.export_data()

    assert response["Content-Type"] == "application/json; charset=utf-8"
    data = json.loads(response.content)
    assert len(data) >= 1


def test_schedule_export_form_target_choices_exclude_draft():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(event=event, user=user)

    target_values = [choice[0] for choice in form.fields["target"].choices]
    expected = ["all"] + [
        state
        for state, _ in SubmissionStates.choices
        if state != SubmissionStates.DRAFT
    ]
    assert target_values == expected


def test_schedule_export_form_has_extra_fields():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(event=event, user=user)

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
    user = make_orga_user(event)
    form = ScheduleExportForm(event=event, user=user)

    for field_name in ScheduleExportForm.Meta.model_fields:
        assert field_name in form.fields, f"Missing model field: {field_name}"


def test_schedule_export_form_questions_property():
    event = EventFactory()
    user = make_orga_user(event)
    sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    form = ScheduleExportForm(event=event, user=user)

    assert list(form.questions) == [sub_q]


def test_schedule_export_form_question_fields_added():
    event = EventFactory()
    user = make_orga_user(event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    form = ScheduleExportForm(event=event, user=user)

    assert f"question_{question.pk}" in form.fields


def test_schedule_export_form_filename():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(event=event, user=user)

    assert form.filename == f"{event.slug}_sessions"


def test_schedule_export_form_export_field_names():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(event=event, user=user)

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


@pytest.mark.parametrize("flag_enabled", (True, False), ids=("enabled", "disabled"))
@pytest.mark.parametrize("field", ("requires_signup", "attendee_signup_count"))
def test_schedule_export_form_signup_fields_follow_flag(flag_enabled, field):
    event = EventFactory(feature_flags={"attendee_signup": flag_enabled})
    user = make_orga_user(event)

    form = ScheduleExportForm(event=event, user=user)

    assert (field in form.fields) is flag_enabled
    assert (field in form.export_field_names) is flag_enabled


def test_schedule_export_form_get_queryset_all():
    event = EventFactory()
    user = make_orga_user(event)
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    form = ScheduleExportForm(
        data={"export_format": "json", "target": ["all"], "title": True},
        event=event,
        user=user,
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert set(qs) == {sub1, sub2}


def test_schedule_export_form_get_queryset_filtered():
    event = EventFactory()
    user = make_orga_user(event)
    sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    form = ScheduleExportForm(
        data={
            "export_format": "json",
            "target": [SubmissionStates.ACCEPTED],
            "title": True,
        },
        event=event,
        user=user,
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert qs == [sub_accepted]


def test_schedule_export_form_get_queryset_excludes_inaccessible():
    """submissions_for_user filters out submissions invisible to the user."""
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(event=event)
    form = ScheduleExportForm(
        data={"export_format": "json", "target": ["all"], "title": True},
        event=event,
        user=speaker.user,
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert qs == []


def test_schedule_export_form_get_queryset_annotates_requires_signup():
    event = EventFactory(feature_flags={"attendee_signup": True})
    user = make_orga_user(event)
    sub = SubmissionFactory(
        event=event, state=SubmissionStates.SUBMITTED, attendee_signup_required=True
    )
    form = ScheduleExportForm(
        data={"export_format": "json", "target": ["all"], "title": True},
        event=event,
        user=user,
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert len(qs) == 1
    assert qs[0]._annotated_requires_signup is True
    assert qs[0]._annotated_confirmed_signup_count == 0
    assert qs[0].pk == sub.pk


def test_schedule_export_form_get_speaker_ids_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_speaker_ids_value(sub)

    assert result == [speaker.code]


def test_schedule_export_form_get_speaker_names_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_speaker_names_value(sub)

    assert result == [speaker.get_display_name()]


def test_schedule_export_form_get_room_value_with_slot():
    event = EventFactory()
    user = make_orga_user(event)
    room = RoomFactory(event=event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    TalkSlotFactory(submission=sub, schedule=wip, room=room)
    freeze_schedule(wip, "v1", notify_speakers=False)
    sub = type(sub).objects.get(pk=sub.pk)
    form = ScheduleExportForm(event=event, user=user)
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
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = getattr(form, method_name)(sub)

    assert result is None


def test_schedule_export_form_get_start_with_slot():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    slot = TalkSlotFactory(submission=sub, schedule=wip)
    freeze_schedule(wip, "v1", notify_speakers=False)
    sub = type(sub).objects.get(pk=sub.pk)
    form = ScheduleExportForm(event=event, user=user)

    start_val = form._get_start_value(sub)
    start_date_val = form._get_start_date_value(sub)
    start_time_val = form._get_start_time_value(sub)

    local_start = slot.start.astimezone(event.tz)
    assert start_val == local_start.isoformat()
    assert start_date_val == local_start.date().isoformat()
    assert start_time_val == local_start.time().isoformat()


def test_schedule_export_form_get_end_with_slot():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    slot = TalkSlotFactory(submission=sub, schedule=wip)
    freeze_schedule(wip, "v1", notify_speakers=False)
    sub = type(sub).objects.get(pk=sub.pk)
    form = ScheduleExportForm(event=event, user=user)

    end_val = form._get_end_value(sub)
    end_date_val = form._get_end_date_value(sub)
    end_time_val = form._get_end_time_value(sub)

    local_end = slot.end.astimezone(event.tz)
    assert end_val == local_end.isoformat()
    assert end_date_val == local_end.date().isoformat()
    assert end_time_val == local_end.time().isoformat()


def test_schedule_export_form_get_duration_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, duration=45)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_duration_value(sub)

    assert result == 45


def test_schedule_export_form_get_image_value_no_image():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_image_value(sub)

    assert result == ""


def test_schedule_export_form_get_created_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_created_value(sub)

    assert result == sub.created.isoformat()


def test_schedule_export_form_get_submission_type_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_submission_type_value(sub)

    assert str(result) == str(sub.submission_type.name)


def test_schedule_export_form_get_track_value():
    event = EventFactory()
    user = make_orga_user(event)
    track = TrackFactory(event=event)
    sub = SubmissionFactory(event=event, track=track)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_track_value(sub)

    assert str(result) == str(track.name)


def test_schedule_export_form_get_track_value_none():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_track_value(sub)

    assert result is None


def test_schedule_export_form_get_tags_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    tag = TagFactory(event=event)
    sub.tags.add(tag)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_tags_value(sub)

    assert result == [tag.tag]


def test_schedule_export_form_get_tags_value_empty():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_tags_value(sub)

    assert result is None


def test_schedule_export_form_get_resources_value():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    resource = ResourceFactory(submission=sub, is_public=True)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_resources_value(sub)

    assert result == [resource.url]


def test_schedule_export_form_get_resources_value_empty():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form._get_resources_value(sub)

    assert result == []


def test_schedule_export_form_get_attendee_signup_count_value():
    event = EventFactory(feature_flags={"attendee_signup": True})
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    sub._annotated_confirmed_signup_count = 3
    form = ScheduleExportForm(event=event, user=user)

    assert form._get_attendee_signup_count_value(sub) == 3


def test_schedule_export_form_get_answer():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    answer = AnswerFactory(question=question, submission=sub)
    form = ScheduleExportForm(event=event, user=user)
    result = form.get_answer(question, sub)

    assert result == answer


def test_schedule_export_form_get_answer_none():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    form = ScheduleExportForm(event=event, user=user)
    result = form.get_answer(question, sub)

    assert result is None


def test_schedule_export_form_question_field_names():
    event = EventFactory()
    user = make_orga_user(event)
    q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    form = ScheduleExportForm(event=event, user=user)

    assert form.question_field_names == [f"question_{q.pk}"]


def test_schedule_export_form_export_fields():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(event=event, user=user)

    field_names = [bf.name for bf in form.export_fields]
    assert "title" in field_names
    assert "speaker_ids" in field_names


def test_schedule_export_form_clean_csv_without_delimiter():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={"export_format": "csv", "target": ["all"], "title": True},
    )

    assert not form.is_valid()
    assert "data_delimiter" in form.errors


def test_schedule_export_form_clean_json_without_delimiter():
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={"export_format": "json", "target": ["all"], "title": True},
    )

    assert form.is_valid(), form.errors


def test_schedule_export_form_get_object_attribute_custom_method():
    """get_object_attribute uses _get_<attr>_value if it exists."""
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, duration=45)
    form = ScheduleExportForm(event=event, user=user)
    result = form.get_object_attribute(sub, "duration")

    assert result == 45


def test_schedule_export_form_get_object_attribute_direct():
    """get_object_attribute falls back to direct attribute access."""
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form.get_object_attribute(sub, "code")

    assert result == sub.code


def test_schedule_export_form_get_object_attribute_missing():
    """get_object_attribute returns None for missing attributes."""
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(event=event, user=user)
    result = form.get_object_attribute(sub, "nonexistent_field")

    assert result is None


def test_schedule_export_form_get_data():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={"export_format": "json", "target": ["all"], "title": True},
    )
    form.is_valid()
    data = form.get_data(form.get_queryset(), ["title"], [])

    assert len(data) == 1
    assert data[0]["ID"] == sub.code
    assert str(sub.title) in str(data[0].values())


def test_schedule_export_form_get_data_with_questions():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    answer = AnswerFactory(question=question, submission=sub)
    form = ScheduleExportForm(event=event, user=user)
    data = form.get_data(form.event.submissions.all(), [], [question])

    assert len(data) == 1
    assert data[0][str(question.question)] == answer.answer_string


def test_schedule_export_form_get_data_without_answer():
    event = EventFactory()
    user = make_orga_user(event)
    SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    form = ScheduleExportForm(event=event, user=user)
    data = form.get_data(form.event.submissions.all(), [], [question])

    assert data[0][str(question.question)] is None


def test_schedule_export_form_export_data_returns_none_when_empty():
    """export_data returns None when no data matches."""
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(
        event=event,
        user=user,
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
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={"export_format": "json", "target": ["all"], "title": True},
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
    user = make_orga_user(event)
    SubmissionFactory(event=event)
    form = ScheduleExportForm(
        event=event,
        user=user,
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
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    sub.speakers.add(speaker1, speaker2)
    form = ScheduleExportForm(
        event=event,
        user=user,
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


def test_schedule_export_form_csv_export_starts_with_utf8_bom():
    """
    Regression check: CSV exports opened in Excel produced mojibake. We
    test for issues seen in the wild and assert the fix:
    1. the UTF-8 BOM
    2. decoding with utf-8-sig (stripping BOM) round-trips
    """
    event = EventFactory()
    user = make_orga_user(event)
    # Use the characters from the user's bug report verbatim.
    SubmissionFactory(
        event=event, title="Beyond “Big” Data: Building Infrastructure for “Thick” Data"
    )
    SubmissionFactory(event=event, title="A Researcher’s Guide – André")
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={
            "export_format": "csv",
            "data_delimiter": "newline",
            "target": ["all"],
            "title": True,
        },
    )
    form.is_valid()
    response = form.export_data()

    assert response.content.startswith(b"\xef\xbb\xbf")
    content = response.content.decode("utf-8-sig")
    assert "Beyond “Big” Data: Building Infrastructure for “Thick” Data" in content
    assert "A Researcher’s Guide – André" in content
    # And a sanity check that the bytes do contain proper UTF-8 sequences,
    # not the MacRoman-interpreted mojibake from the bug report.
    assert "Andr√" not in content
    assert "‚Äú" not in content


def test_schedule_export_form_export_data_with_question():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    answer = AnswerFactory(question=question, submission=sub)
    form = ScheduleExportForm(
        event=event,
        user=user,
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


def test_speaker_export_form_target_choices():
    event = EventFactory()
    form = SpeakerExportForm(event=event)

    target_values = [choice[0] for choice in form.fields["target"].choices]
    assert target_values == ["all", "accepted"]


def test_speaker_export_form_has_extra_fields():
    event = EventFactory()
    form = SpeakerExportForm(event=event)

    for field_name in ("email", "submission_ids", "submission_titles", "avatar"):
        assert field_name in form.fields, f"Missing field: {field_name}"


def test_speaker_export_form_has_model_fields():
    event = EventFactory()
    form = SpeakerExportForm(event=event)

    for field_name in SpeakerExportForm.Meta.model_fields:
        assert field_name in form.fields, f"Missing model field: {field_name}"


def test_speaker_export_form_questions_property():
    """Only active speaker-targeted questions are included."""
    event = EventFactory()
    speaker_q = QuestionFactory(event=event, target="speaker", active=True)
    QuestionFactory(event=event, target="submission", active=True)
    QuestionFactory(event=event, target="speaker", active=False)
    form = SpeakerExportForm(event=event)

    assert list(form.questions) == [speaker_q]


def test_speaker_export_form_question_fields_added():
    event = EventFactory()
    question = QuestionFactory(event=event, target="speaker", active=True)
    form = SpeakerExportForm(event=event)

    assert f"question_{question.pk}" in form.fields


def test_speaker_export_form_filename():
    event = EventFactory()
    form = SpeakerExportForm(event=event)

    assert form.filename == f"{event.slug}_speakers"


def test_speaker_export_form_export_field_names():
    event = EventFactory()
    form = SpeakerExportForm(event=event)

    names = form.export_field_names
    assert names == [
        "name",
        "biography",
        "email",
        "avatar",
        "submission_ids",
        "submission_titles",
    ]


def test_speaker_export_form_get_queryset_all():
    event = EventFactory()
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub1.speakers.add(speaker1)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    sub2.speakers.add(speaker2)
    form = SpeakerExportForm(
        data={"export_format": "json", "target": "all", "name": True}, event=event
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert set(qs) == {speaker1, speaker2}


def test_speaker_export_form_get_queryset_accepted_only():
    event = EventFactory()
    accepted_speaker = SpeakerFactory(event=event)
    submitted_speaker = SpeakerFactory(event=event)
    sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    sub_accepted.speakers.add(accepted_speaker)
    sub_submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub_submitted.speakers.add(submitted_speaker)
    form = SpeakerExportForm(
        data={"export_format": "json", "target": "accepted", "name": True}, event=event
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert qs == [accepted_speaker]


def test_speaker_export_form_get_queryset_includes_confirmed():
    event = EventFactory()
    confirmed_speaker = SpeakerFactory(event=event)
    sub_confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub_confirmed.speakers.add(confirmed_speaker)
    form = SpeakerExportForm(
        data={"export_format": "json", "target": "accepted", "name": True}, event=event
    )
    form.is_valid()
    qs = list(form.get_queryset())

    assert qs == [confirmed_speaker]


def test_speaker_export_form_get_name_value():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    form = SpeakerExportForm(event=event)
    result = form._get_name_value(speaker)

    assert result == speaker.get_display_name()


def test_speaker_export_form_get_avatar_value_no_avatar():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    form = SpeakerExportForm(event=event)
    result = form._get_avatar_value(speaker)

    assert result is None


def test_speaker_export_form_get_email_value():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    form = SpeakerExportForm(event=event)
    result = form._get_email_value(speaker)

    assert result == speaker.user.email


def test_speaker_export_form_get_submission_ids_value():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    form = SpeakerExportForm(event=event)
    result = form._get_submission_ids_value(speaker)

    assert result == [sub.code]


def test_speaker_export_form_get_submission_titles_value():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    form = SpeakerExportForm(event=event)
    result = form._get_submission_titles_value(speaker)

    assert result == [sub.title]


def test_speaker_export_form_get_answer():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target="speaker", active=True)
    answer = AnswerFactory(question=question, speaker=speaker)
    form = SpeakerExportForm(event=event)
    result = form.get_answer(question, speaker)

    assert result == answer


def test_speaker_export_form_get_answer_none():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target="speaker", active=True)
    form = SpeakerExportForm(event=event)
    result = form.get_answer(question, speaker)

    assert result is None
