# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest

from pretalx.orga.forms.export import (
    ReviewExportForm,
    ScheduleExportForm,
    SpeakerExportForm,
)
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import QuestionTarget, Submission, SubmissionStates
from tests.factories import (
    AnswerFactory,
    AttendeeSignupFactory,
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

SCHEDULE_FIELD_NAMES = [
    "title",
    "state",
    "pending_state",
    "submission_type",
    "track",
    "created",
    "tags",
    "abstract",
    "description",
    "notes",
    "internal_notes",
    "duration",
    "slot_count",
    "content_locale",
    "is_featured",
    "do_not_record",
    "image",
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


def test_review_export_form_single_score_category_has_no_score_fields():
    event = EventFactory()
    user = make_orga_user(event)
    ReviewScoreCategoryFactory(event=event, active=False)

    form = ReviewExportForm(
        event=event, user=user, data={"export_format": "csv", "target": "all"}
    )

    assert form.is_valid(), form.errors
    assert form.score_categories == []
    assert form.export_field_names == [
        "score",
        "text",
        "submission_id",
        "submission_title",
        "created",
        "updated",
        "user_name",
        "user_email",
    ]
    assert [name for name in form.fields if name.startswith("score_")] == []


def test_review_export_form_multiple_score_categories():
    event = EventFactory()
    user = make_orga_user(event)
    default_cat = event.score_categories.first()
    cat2 = ReviewScoreCategoryFactory(event=event, active=True, name="Second")
    score = ReviewScoreFactory(category=cat2, value=5)
    scored = ReviewFactory(submission__event=event)
    scored.scores.add(score)
    unscored = ReviewFactory(submission__event=event)

    form = ReviewExportForm(event=event, user=user)

    assert set(form.score_categories) == {default_cat, cat2}
    assert form.export_field_names == [
        "score",
        "text",
        f"score_{default_cat.pk}",
        f"score_{cat2.pk}",
        "submission_id",
        "submission_title",
        "created",
        "updated",
        "user_name",
        "user_email",
    ]
    assert str(form.fields[f"score_{cat2.pk}"].label) == "Score in “Second”"
    assert form.get_additional_data(scored) == {
        str(default_cat.name): None,
        "Second": 5,
    }
    assert form.get_additional_data(unscored) == {
        str(default_cat.name): None,
        "Second": None,
    }


def test_review_export_form_value_getters_and_answers():
    event = EventFactory()
    user = make_orga_user(event)
    reviewer_q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True
    )
    QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, active=True)
    review = ReviewFactory(submission__event=event)
    unanswered = ReviewFactory(submission__event=event)
    answer = AnswerFactory(question=reviewer_q, review=review, answer="42")

    form = ReviewExportForm(event=event, user=user)

    assert set(form.questions) == {reviewer_q}
    assert form._get_submission_id_value(review) == review.submission.code
    assert form._get_submission_title_value(review) == review.submission.title
    assert form._get_user_name_value(review) == review.user.name
    assert form._get_user_email_value(review) == review.user.email
    assert form.get_answer(reviewer_q, review) == answer
    assert form.get_answer(reviewer_q, unanswered) is None


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("all", {"accepted", "confirmed", "rejected"}),
        ("accepted", {"accepted"}),
        ("confirmed", {"confirmed"}),
        ("rejected", {"rejected"}),
    ),
)
def test_review_export_form_get_queryset_filters_by_target_and_excludes_own(
    target, expected
):
    event = EventFactory()
    user = make_orga_user(event)
    for state in ("accepted", "confirmed", "rejected"):
        ReviewFactory(
            submission=SubmissionFactory(event=event, state=state, title=state)
        )
    own = SubmissionFactory(event=event, state="accepted", title="own")
    own.speakers.add(SpeakerFactory(event=event, user=user))
    ReviewFactory(submission=own)

    form = ReviewExportForm(
        event=event, user=user, data={"export_format": "json", "target": target}
    )
    assert form.is_valid(), form.errors

    assert {review.submission.title for review in form.get_queryset()} == expected


def test_review_export_form_export_data_json():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    ReviewFactory(submission=sub, score=3)
    form = ReviewExportForm(
        event=event,
        user=user,
        data={
            "export_format": "json",
            "target": "all",
            "score": True,
            "submission_id": True,
        },
    )
    assert form.is_valid(), form.errors

    response = form.export_data()

    assert response["Content-Type"] == "application/json; charset=utf-8"
    assert response["Content-Disposition"] == (
        f'attachment; filename="{event.slug}_reviews.json"'
    )
    assert json.loads(response.content) == [{"Score": "3.00", "Proposal ID": sub.code}]


def test_schedule_export_form_fields():
    event = EventFactory()
    user = make_orga_user(event)
    sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    QuestionFactory(event=event, target=QuestionTarget.SPEAKER)

    form = ScheduleExportForm(event=event, user=user)

    assert [choice[0] for choice in form.fields["target"].choices] == [
        "all",
        *[
            state
            for state, _ in SubmissionStates.choices
            if state != SubmissionStates.DRAFT
        ],
    ]
    assert list(form.questions) == [sub_q]
    assert form.question_field_names == [f"question_{sub_q.pk}"]
    assert form.export_field_names == SCHEDULE_FIELD_NAMES
    assert [bf.name for bf in form.export_fields] == [
        *SCHEDULE_FIELD_NAMES,
        f"question_{sub_q.pk}",
    ]


@pytest.mark.parametrize("flag_enabled", (True, False), ids=("enabled", "disabled"))
def test_schedule_export_form_signup_fields_follow_flag(flag_enabled):
    event = EventFactory(feature_flags={"attendee_signup": flag_enabled})
    user = make_orga_user(event)

    form = ScheduleExportForm(event=event, user=user)

    for field in ("requires_signup", "attendee_signup_count"):
        assert (field in form.fields) is flag_enabled
        assert (field in form.export_field_names) is flag_enabled


@pytest.mark.parametrize(
    ("target", "expected"),
    ((["all"], {"submitted", "accepted"}), ([SubmissionStates.ACCEPTED], {"accepted"})),
    ids=("all", "accepted"),
)
def test_schedule_export_form_get_queryset(target, expected):
    event = EventFactory()
    user = make_orga_user(event)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED, title="submitted")
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED, title="accepted")
    form = ScheduleExportForm(
        data={"export_format": "json", "target": target, "title": True},
        event=event,
        user=user,
    )
    assert form.is_valid(), form.errors

    assert {sub.title for sub in form.get_queryset()} == expected


def test_schedule_export_form_get_queryset_excludes_inaccessible():
    event = EventFactory()
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(event=event)
    form = ScheduleExportForm(
        data={"export_format": "json", "target": ["all"], "title": True},
        event=event,
        user=speaker.user,
    )
    assert form.is_valid(), form.errors

    assert list(form.get_queryset()) == []


def test_schedule_export_form_get_queryset_annotates_signup_data():
    event = EventFactory(feature_flags={"attendee_signup": True})
    user = make_orga_user(event)
    sub = SubmissionFactory(
        event=event, state=SubmissionStates.SUBMITTED, attendee_signup_required=True
    )
    AttendeeSignupFactory(submission=sub)
    form = ScheduleExportForm(
        data={"export_format": "json", "target": ["all"], "title": True},
        event=event,
        user=user,
    )
    assert form.is_valid(), form.errors

    qs = list(form.get_queryset())

    assert [s.pk for s in qs] == [sub.pk]
    assert qs[0]._annotated_requires_signup is True
    assert qs[0]._annotated_confirmed_signup_count == 1
    assert form._get_attendee_signup_count_value(qs[0]) == 1


def test_schedule_export_form_value_getters_without_slot():
    event = EventFactory()
    user = make_orga_user(event)
    track = TrackFactory(event=event)
    sub = SubmissionFactory(event=event, track=track, duration=45)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    tag = TagFactory(event=event)
    sub.tags.add(tag)
    resource = ResourceFactory(submission=sub, is_public=True)
    bare = SubmissionFactory(event=event)

    form = ScheduleExportForm(event=event, user=user)

    assert form._get_speaker_ids_value(sub) == [speaker.code]
    assert form._get_speaker_names_value(sub) == [speaker.get_display_name()]
    assert form._get_duration_value(sub) == 45
    assert form.get_object_attribute(sub, "duration") == 45
    assert form.get_object_attribute(sub, "code") == sub.code
    assert form.get_object_attribute(sub, "nonexistent_field") is None
    assert form._get_image_value(sub) == ""
    assert form._get_created_value(sub) == sub.created.isoformat()
    assert str(form._get_submission_type_value(sub)) == str(sub.submission_type.name)
    assert str(form._get_track_value(sub)) == str(track.name)
    assert form._get_tags_value(sub) == [tag.tag]
    assert form._get_resources_value(sub) == [resource.url]
    assert form._get_track_value(bare) is None
    assert form._get_tags_value(bare) is None
    assert form._get_resources_value(bare) == []
    for method_name in (
        "_get_room_value",
        "_get_start_value",
        "_get_start_date_value",
        "_get_start_time_value",
        "_get_end_value",
        "_get_end_date_value",
        "_get_end_time_value",
    ):
        assert getattr(form, method_name)(bare) is None, method_name


def test_schedule_export_form_slot_getters():
    event = EventFactory()
    user = make_orga_user(event)
    room = RoomFactory(event=event)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    slot = TalkSlotFactory(submission=sub, schedule=wip, room=room)
    freeze_schedule(wip, "v1", notify_speakers=False)
    sub = Submission.objects.select_related("event").get(pk=sub.pk)
    form = ScheduleExportForm(event=event, user=user)

    local_start = slot.start.astimezone(event.tz)
    local_end = slot.end.astimezone(event.tz)
    assert str(form._get_room_value(sub)) == str(room.name)
    assert form._get_start_value(sub) == local_start.isoformat()
    assert form._get_start_date_value(sub) == local_start.date().isoformat()
    assert form._get_start_time_value(sub) == local_start.time().isoformat()
    assert form._get_end_value(sub) == local_end.isoformat()
    assert form._get_end_date_value(sub) == local_end.date().isoformat()
    assert form._get_end_time_value(sub) == local_end.time().isoformat()


def test_schedule_export_form_answers():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event, title="Answered")
    unanswered = SubmissionFactory(event=event, title="Unanswered")
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
    assert form.is_valid(), form.errors

    assert form.get_answer(question, sub) == answer
    assert form.get_answer(question, unanswered) is None
    assert sorted(
        form.get_data(event.submissions.all(), [], [question]),
        key=lambda row: row["ID"],
    ) == sorted(
        [
            {"ID": sub.code, str(question.question): answer.answer_string},
            {"ID": unanswered.code, str(question.question): None},
        ],
        key=lambda row: row["ID"],
    )
    response = form.export_data()
    assert {
        row["ID"]: row[str(question.question)] for row in json.loads(response.content)
    } == {sub.code: answer.answer_string, unanswered.code: None}


@pytest.mark.parametrize(
    ("export_format", "errors"),
    (
        ("csv", {"data_delimiter": ["Please select a delimiter for your CSV export."]}),
        ("json", {}),
    ),
)
def test_schedule_export_form_clean_requires_csv_delimiter(export_format, errors):
    event = EventFactory()
    user = make_orga_user(event)
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={"export_format": export_format, "target": ["all"], "title": True},
    )

    assert form.is_valid() == (not errors)
    assert form.errors == errors


def test_schedule_export_form_export_data_json():
    event = EventFactory()
    user = make_orga_user(event)
    sub = SubmissionFactory(event=event)

    empty = ScheduleExportForm(
        event=event,
        user=user,
        data={
            "export_format": "json",
            "target": [SubmissionStates.ACCEPTED],
            "title": True,
        },
    )
    assert empty.is_valid(), empty.errors
    assert empty.export_data() is None

    form = ScheduleExportForm(
        event=event,
        user=user,
        data={"export_format": "json", "target": ["all"], "title": True},
    )
    assert form.is_valid(), form.errors
    response = form.export_data()

    assert response["Content-Type"] == "application/json; charset=utf-8"
    assert response["Content-Disposition"] == (
        f'attachment; filename="{event.slug}_sessions.json"'
    )
    assert json.loads(response.content) == [
        {"ID": sub.code, "Proposal title": sub.title}
    ]


def test_schedule_export_form_export_data_csv():
    event = EventFactory()
    user = make_orga_user(event)
    # Use the characters from the user's bug report verbatim.
    sub = SubmissionFactory(event=event, title="A Researcher’s Guide – André")
    speaker1 = SpeakerFactory(event=event, user__name="Ada")
    speaker2 = SpeakerFactory(event=event, user__name="Bob")
    sub.speakers.add(speaker1, through_defaults={"position": 0})
    sub.speakers.add(speaker2, through_defaults={"position": 1})
    form = ScheduleExportForm(
        event=event,
        user=user,
        data={
            "export_format": "csv",
            "data_delimiter": "comma",
            "target": ["all"],
            "title": True,
            "speaker_names": True,
        },
    )
    assert form.is_valid(), form.errors

    response = form.export_data()

    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert response["Content-Disposition"] == (
        f'attachment; filename="{event.slug}_sessions.csv"'
    )
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.content.decode("utf-8-sig") == (
        "ID,Proposal title,Speaker names\r\n"
        f'{sub.code},A Researcher’s Guide – André,"Ada, Bob"\r\n'
    )


def test_speaker_export_form_fields():
    event = EventFactory()
    speaker_q = QuestionFactory(event=event, target="speaker", active=True)
    QuestionFactory(event=event, target="submission", active=True)
    QuestionFactory(event=event, target="speaker", active=False)

    form = SpeakerExportForm(event=event)

    assert list(form.questions) == [speaker_q]
    assert form.export_field_names == [
        "name",
        "biography",
        "email",
        "avatar",
        "submission_ids",
        "submission_titles",
    ]
    assert [bf.name for bf in form.export_fields] == [
        *form.export_field_names,
        f"question_{speaker_q.pk}",
    ]


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("all", {"submitted", "accepted", "confirmed"}),
        ("accepted", {"accepted", "confirmed"}),
    ),
)
def test_speaker_export_form_get_queryset(target, expected):
    event = EventFactory()
    for state in ("submitted", "accepted", "confirmed"):
        SubmissionFactory(event=event, state=state).speakers.add(
            SpeakerFactory(event=event, user__name=state)
        )
    form = SpeakerExportForm(
        data={"export_format": "json", "target": target, "name": True}, event=event
    )
    assert form.is_valid(), form.errors

    assert {speaker.user.name for speaker in form.get_queryset()} == expected


def test_speaker_export_form_value_getters():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    managed = SpeakerFactory(event=event, user=None, email="contact@example.com")
    bare = SpeakerFactory(event=event, user=None, email=None)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    question = QuestionFactory(event=event, target="speaker", active=True)
    answer = AnswerFactory(question=question, speaker=speaker)

    form = SpeakerExportForm(event=event)

    assert form._get_name_value(speaker) == speaker.get_display_name()
    assert form._get_avatar_value(speaker) is None
    assert form._get_email_value(speaker) == speaker.user.email
    assert form._get_email_value(managed) == "contact@example.com"
    assert form._get_email_value(bare) is None
    assert form._get_submission_ids_value(speaker) == [sub.code]
    assert form._get_submission_titles_value(speaker) == [sub.title]
    assert form._get_submission_ids_value(bare) == []
    assert form.get_answer(question, speaker) == answer
    assert form.get_answer(question, bare) is None
