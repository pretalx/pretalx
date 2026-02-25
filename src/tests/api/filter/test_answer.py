import pytest
from django_scopes import scopes_disabled

from pretalx.api.filters.answer import AnswerFilterSet
from pretalx.submission.models import Answer
from tests.factories import (
    AnswerFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_answer_filter_filters_by_question(event):
    with scopes_disabled():
        q1 = QuestionFactory(event=event)
        q2 = QuestionFactory(event=event)
        sub = SubmissionFactory(event=event)
        a1 = AnswerFactory(question=q1, submission=sub)
        AnswerFactory(question=q2, submission=sub)

        fs = AnswerFilterSet(
            data={"question": str(q1.pk)}, queryset=Answer.objects.all()
        )

    assert list(fs.qs) == [a1]


@pytest.mark.django_db
def test_answer_filter_filters_by_submission_code(event):
    with scopes_disabled():
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        q = QuestionFactory(event=event)
        a1 = AnswerFactory(question=q, submission=sub1)
        AnswerFactory(question=q, submission=sub2)

        fs = AnswerFilterSet(
            data={"submission": sub1.code}, queryset=Answer.objects.all()
        )

    assert list(fs.qs) == [a1]


@pytest.mark.django_db
def test_answer_filter_submission_code_is_case_insensitive(event):
    with scopes_disabled():
        sub = SubmissionFactory(event=event)
        q = QuestionFactory(event=event)
        a = AnswerFactory(question=q, submission=sub)

        fs = AnswerFilterSet(
            data={"submission": sub.code.lower()}, queryset=Answer.objects.all()
        )

    assert list(fs.qs) == [a]


@pytest.mark.django_db
def test_answer_filter_filters_by_speaker_code(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        q = QuestionFactory(event=event, target="speaker")
        a1 = AnswerFactory(question=q, submission=None, speaker=speaker)
        AnswerFactory(question=q, submission=None, speaker=SpeakerFactory(event=event))

        fs = AnswerFilterSet(
            data={"speaker": speaker.code}, queryset=Answer.objects.all()
        )

    assert list(fs.qs) == [a1]


@pytest.mark.django_db
def test_answer_filter_filters_by_review(event):
    with scopes_disabled():
        sub = SubmissionFactory(event=event)
        q = QuestionFactory(event=event, target="reviewer")
        review1 = ReviewFactory(submission=sub)
        review2 = ReviewFactory(submission=sub)
        a1 = AnswerFactory(question=q, submission=None, review=review1)
        AnswerFactory(question=q, submission=None, review=review2)

        fs = AnswerFilterSet(
            data={"review": str(review1.pk)}, queryset=Answer.objects.all()
        )

    assert list(fs.qs) == [a1]
