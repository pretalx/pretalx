import pytest
from django_scopes import scopes_disabled

from pretalx.submission.forms.question import QuestionsForm
from pretalx.submission.models import QuestionTarget, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("active", "should_have_field"), ((True, True), (False, False))
)
def test_questions_form_init_filters_by_active_flag(active, should_have_field):
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, active=active
        )

        form = QuestionsForm(event=event)

    assert (f"question_{q.pk}" in form.fields) == should_have_field


@pytest.mark.django_db
def test_questions_form_init_filters_by_target_type():
    with scopes_disabled():
        event = EventFactory()
        sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)

        form = QuestionsForm(event=event, target=QuestionTarget.SUBMISSION)

    assert f"question_{sub_q.pk}" in form.fields
    assert f"question_{speaker_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_init_no_target_excludes_reviewer_questions():
    """When target is None, all non-reviewer questions are included."""
    with scopes_disabled():
        event = EventFactory()
        sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
        reviewer_q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)

        form = QuestionsForm(event=event, target=None)

    assert f"question_{sub_q.pk}" in form.fields
    assert f"question_{speaker_q.pk}" in form.fields
    assert f"question_{reviewer_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_init_filters_by_track():
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        track_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        track_q.tracks.add(track)
        general_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        other_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        other_q.tracks.add(other_track)

        form = QuestionsForm(event=event, track=track)

    assert f"question_{track_q.pk}" in form.fields
    assert f"question_{general_q.pk}" in form.fields
    assert f"question_{other_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_init_filters_by_submission_type():
    with scopes_disabled():
        event = EventFactory()
        sub_type = SubmissionTypeFactory(event=event)
        other_type = SubmissionTypeFactory(event=event)
        typed_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        typed_q.submission_types.add(sub_type)
        general_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        other_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        other_q.submission_types.add(other_type)

        form = QuestionsForm(event=event, submission_type=sub_type)

    assert f"question_{typed_q.pk}" in form.fields
    assert f"question_{general_q.pk}" in form.fields
    assert f"question_{other_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_init_skip_limited_questions():
    """skip_limited_questions=True includes only questions without track/type limits."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        general_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        limited_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        limited_q.tracks.add(track)

        form = QuestionsForm(event=event, skip_limited_questions=True)

    assert f"question_{general_q.pk}" in form.fields
    assert f"question_{limited_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_init_for_reviewers_filter():
    with scopes_disabled():
        event = EventFactory()
        visible_q = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, is_visible_to_reviewers=True
        )
        hidden_q = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, is_visible_to_reviewers=False
        )

        form = QuestionsForm(event=event, for_reviewers=True)

    assert f"question_{visible_q.pk}" in form.fields
    assert f"question_{hidden_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_init_loads_existing_answer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        submission = SubmissionFactory(event=event)
        answer = AnswerFactory(question=q, submission=submission, answer="42")

        form = QuestionsForm(event=event, submission=submission)

    field = form.fields[f"question_{q.pk}"]
    assert field.initial == "42"
    assert field.answer == answer


@pytest.mark.django_db
def test_questions_form_init_loads_file_answer_initial():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.FILE
        )
        submission = SubmissionFactory(event=event)
        answer = AnswerFactory(
            question=q, submission=submission, answer="file://test.pdf"
        )
        answer.answer_file.name = "test.pdf"
        answer.save()

        form = QuestionsForm(event=event, submission=submission)

    field = form.fields[f"question_{q.pk}"]
    assert field.initial == answer.answer_file


@pytest.mark.django_db
def test_questions_form_get_object_for_question_submission():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        submission = SubmissionFactory(event=event)

        form = QuestionsForm(event=event, submission=submission)

    assert form.get_object_for_question(q) == submission


@pytest.mark.django_db
def test_questions_form_get_object_for_question_speaker():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
        speaker = SpeakerFactory(event=event)

        form = QuestionsForm(
            event=event, speaker=speaker, target=QuestionTarget.SPEAKER
        )

    assert form.get_object_for_question(q) == speaker


@pytest.mark.django_db
def test_questions_form_get_object_for_question_reviewer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
        review = ReviewFactory(submission__event=event)

        form = QuestionsForm(event=event, review=review, target=QuestionTarget.REVIEWER)

    assert form.get_object_for_question(q) == review


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("prop_name", "included_target", "excluded_target"),
    (
        ("speaker_fields", QuestionTarget.SPEAKER, QuestionTarget.SUBMISSION),
        ("submission_fields", QuestionTarget.SUBMISSION, QuestionTarget.SPEAKER),
    ),
)
def test_questions_form_fields_property_filters_by_target(
    prop_name, included_target, excluded_target
):
    with scopes_disabled():
        event = EventFactory()
        included_q = QuestionFactory(event=event, target=included_target)
        excluded_q = QuestionFactory(event=event, target=excluded_target)

        form = QuestionsForm(event=event, target=None)

    field_names = [f.name for f in getattr(form, prop_name)]
    assert f"question_{included_q.pk}" in field_names
    assert f"question_{excluded_q.pk}" not in field_names


@pytest.mark.django_db
def test_questions_form_serialize_answers_with_existing_answer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        submission = SubmissionFactory(event=event)
        AnswerFactory(question=q, submission=submission, answer="My answer")

        form = QuestionsForm(event=event, submission=submission)

    serialized = form.serialize_answers()
    assert serialized[f"question-{q.pk}"] == "My answer"


@pytest.mark.django_db
def test_questions_form_serialize_answers_without_answer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)

        form = QuestionsForm(event=event)

    serialized = form.serialize_answers()
    assert serialized[f"question-{q.pk}"] is None


@pytest.mark.django_db
def test_questions_form_save_creates_answer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
        )
        submission = SubmissionFactory(event=event)

        form = QuestionsForm(
            event=event, submission=submission, data={f"question_{q.pk}": "New answer"}
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = submission.answers.get(question=q)

    assert answer.answer == "New answer"


@pytest.mark.django_db
def test_questions_form_save_updates_existing_answer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
        )
        submission = SubmissionFactory(event=event)
        AnswerFactory(question=q, submission=submission, answer="Old answer")

        form = QuestionsForm(
            event=event,
            submission=submission,
            data={f"question_{q.pk}": "Updated answer"},
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = submission.answers.get(question=q)

    assert answer.answer == "Updated answer"


@pytest.mark.django_db
def test_questions_form_save_deletes_answer_when_empty():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
        )
        submission = SubmissionFactory(event=event)
        AnswerFactory(question=q, submission=submission, answer="Old answer")

        form = QuestionsForm(
            event=event, submission=submission, data={f"question_{q.pk}": ""}
        )
        assert form.is_valid(), form.errors
        form.save()

        assert not submission.answers.filter(question=q).exists()


@pytest.mark.django_db
def test_questions_form_save_choice_question():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.CHOICES,
        )
        option = AnswerOptionFactory(question=q)
        submission = SubmissionFactory(event=event)

        form = QuestionsForm(
            event=event,
            submission=submission,
            data={f"question_{q.pk}": str(option.pk)},
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = submission.answers.get(question=q)

    assert answer.answer == option.answer
    with scopes_disabled():
        assert list(answer.options.all()) == [option]


@pytest.mark.django_db
def test_questions_form_save_multiple_choice_question():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.MULTIPLE,
        )
        opt1 = AnswerOptionFactory(question=q)
        opt2 = AnswerOptionFactory(question=q)
        submission = SubmissionFactory(event=event)

        form = QuestionsForm(
            event=event,
            submission=submission,
            data={f"question_{q.pk}": [str(opt1.pk), str(opt2.pk)]},
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = submission.answers.get(question=q)

    with scopes_disabled():
        assert set(answer.options.all()) == {opt1, opt2}


@pytest.mark.django_db
def test_questions_form_save_boolean_question():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.BOOLEAN,
        )
        submission = SubmissionFactory(event=event)

        form = QuestionsForm(
            event=event, submission=submission, data={f"question_{q.pk}": "True"}
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = submission.answers.get(question=q)

    assert answer.answer == "True"


@pytest.mark.django_db
def test_questions_form_init_uses_default_answer():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
            default_answer="Default value",
        )

        form = QuestionsForm(event=event)

    field = form.fields[f"question_{q.pk}"]
    assert field.initial == "Default value"


@pytest.mark.django_db
def test_questions_form_init_readonly_disables_fields():
    with scopes_disabled():
        event = EventFactory()
        QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)

        form = QuestionsForm(event=event, readonly=True)

    for field in form.fields.values():
        assert field.disabled is True


@pytest.mark.django_db
def test_questions_form_init_track_from_submission():
    """When no track is explicitly provided, submission.track is used."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        track_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        track_q.tracks.add(track)
        other_track = TrackFactory(event=event)
        other_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        other_q.tracks.add(other_track)

        form = QuestionsForm(event=event, submission=submission)

    assert f"question_{track_q.pk}" in form.fields
    assert f"question_{other_q.pk}" not in form.fields


@pytest.mark.django_db
def test_questions_form_save_speaker_question():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
        )
        speaker = SpeakerFactory(event=event)

        form = QuestionsForm(
            event=event,
            speaker=speaker,
            target=QuestionTarget.SPEAKER,
            data={f"question_{q.pk}": "Speaker answer"},
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = speaker.answers.get(question=q)

    assert answer.answer == "Speaker answer"


@pytest.mark.django_db
def test_questions_form_save_reviewer_question():
    with scopes_disabled():
        event = EventFactory()
        q = QuestionFactory(
            event=event, target=QuestionTarget.REVIEWER, variant=QuestionVariant.STRING
        )
        review = ReviewFactory(submission__event=event)

        form = QuestionsForm(
            event=event,
            review=review,
            target=QuestionTarget.REVIEWER,
            data={f"question_{q.pk}": "Reviewer answer"},
        )
        assert form.is_valid(), form.errors
        form.save()

        answer = review.answers.get(question=q)

    assert answer.answer == "Reviewer answer"
