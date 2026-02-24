import pytest

from tests.factories import FeedbackFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_feedback_str():
    feedback = FeedbackFactory(rating=4)

    result = str(feedback)

    assert (
        result
        == f"Feedback(event={feedback.talk.event.slug}, talk={feedback.talk.title}, rating=4)"
    )


@pytest.mark.django_db
def test_feedback_event():
    feedback = FeedbackFactory()
    assert feedback.event == feedback.talk.event
