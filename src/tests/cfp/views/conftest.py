import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.person.models import User
from pretalx.submission.models import AnswerOption, SubmissionType
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
)


def get_response_and_url(client, url, follow=True, method="POST", data=None):
    """Follow a request and return (response, final_url)."""
    if method == "GET":
        response = client.get(url, follow=follow, data=data)
    else:
        response = client.post(url, follow=follow, data=data)
    try:
        current_url = response.redirect_chain[-1][0]
    except IndexError:
        current_url = url
    return response, current_url


def start_wizard(client, event, access_code=None):
    """Navigate to the wizard start, return (response, info_url)."""
    url = f"/{event.slug}/submit/"
    if access_code:
        url += f"?access_code={access_code.code}"
    return get_response_and_url(client, url, method="GET")


def info_data(event, submission_type=None, title="Submission title", **overrides):
    """Build the standard info step POST data."""
    with scopes_disabled():
        if submission_type is None:
            submission_type = SubmissionType.objects.filter(event=event).first().pk
        elif hasattr(submission_type, "pk"):
            submission_type = submission_type.pk
    data = {
        "title": title,
        "content_locale": "en",
        "description": "Description",
        "abstract": "Abstract",
        "notes": "Notes",
        "slot_count": 1,
        "submission_type": submission_type,
        "additional_speaker": "",
        "resource-TOTAL_FORMS": "0",
        "resource-INITIAL_FORMS": "0",
        "resource-MIN_NUM_FORMS": "0",
        "resource-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


@pytest.fixture
def cfp_event():
    """An event with an open CfP (deadline in the future)."""
    with scopes_disabled():
        event = EventFactory(is_public=True)
        event.cfp.deadline = now() + dt.timedelta(days=30)
        event.cfp.save()
    return event


@pytest.fixture
def cfp_user():
    """A user with known credentials for CfP wizard tests."""
    with scopes_disabled():
        return User.objects.create_user(
            email="testuser@example.com", password="testpassw0rd!", name="Test User"
        )


@pytest.fixture
def submission_question(cfp_event):
    """A submission-targeted number question for the CfP event."""
    with scopes_disabled():
        return QuestionFactory(
            event=cfp_event,
            question="How much do you like green, on a scale from 1-10?",
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            position=1,
        )


@pytest.fixture
def speaker_question(cfp_event):
    """A speaker-targeted string question for the CfP event."""
    with scopes_disabled():
        return QuestionFactory(
            event=cfp_event,
            question="What is your favourite color?",
            variant=QuestionVariant.STRING,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
            position=3,
        )


@pytest.fixture
def review_question(cfp_event):
    """A reviewer-targeted question (should not appear in CfP)."""
    with scopes_disabled():
        return QuestionFactory(
            event=cfp_event,
            question="Reviewer only question",
            variant=QuestionVariant.STRING,
            target="reviewer",
            question_required=QuestionRequired.REQUIRED,
            position=4,
        )


@pytest.fixture
def choice_question(cfp_event):
    """A speaker-targeted choice question with three options."""
    with scopes_disabled():
        question = QuestionFactory(
            event=cfp_event,
            question="How much do you like green?",
            variant=QuestionVariant.CHOICES,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
            position=9,
        )
        for answer in ("very", "incredibly", "omggreen"):
            AnswerOption.objects.create(question=question, answer=answer)
    return question


@pytest.fixture
def multiple_choice_question(cfp_event):
    """A speaker-targeted multiple choice question with three options."""
    with scopes_disabled():
        question = QuestionFactory(
            event=cfp_event,
            question="Which colors other than green do you like?",
            variant=QuestionVariant.MULTIPLE,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
            position=10,
        )
        for answer in ("yellow", "blue", "black"):
            AnswerOption.objects.create(question=question, answer=answer)
    return question


@pytest.fixture
def file_question(cfp_event):
    """A submission-targeted file question."""
    with scopes_disabled():
        return QuestionFactory(
            event=cfp_event,
            question="Please submit your paper.",
            variant=QuestionVariant.FILE,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            position=7,
        )


@pytest.fixture
def cfp_track(cfp_event):
    """A track for the CfP event, with use_tracks enabled."""
    with scopes_disabled():
        cfp_event.feature_flags["use_tracks"] = True
        cfp_event.save()
        return TrackFactory(event=cfp_event, name="Test Track")


@pytest.fixture
def cfp_other_track(cfp_event):
    """A second track for the CfP event."""
    with scopes_disabled():
        cfp_event.feature_flags["use_tracks"] = True
        cfp_event.save()
        return TrackFactory(event=cfp_event, name="Second Track")


@pytest.fixture
def cfp_access_code(cfp_event):
    """A valid access code for the CfP event."""
    with scopes_disabled():
        return SubmitterAccessCodeFactory(event=cfp_event)
