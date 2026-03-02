# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.person.models import User
from pretalx.submission.models import SubmissionType
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    AnswerOptionFactory,
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
    event = EventFactory(is_public=True)
    event.cfp.deadline = now() + dt.timedelta(days=30)
    event.cfp.save()
    return event


@pytest.fixture
def cfp_user():
    """A user with known credentials for CfP wizard tests."""
    return User.objects.create_user(
        email="testuser@example.com", password="testpassw0rd!", name="Test User"
    )


@pytest.fixture
def choice_question(cfp_event):
    """A speaker-targeted choice question with three options."""
    question = QuestionFactory(
        event=cfp_event,
        question="How much do you like green?",
        variant=QuestionVariant.CHOICES,
        target="speaker",
        question_required=QuestionRequired.OPTIONAL,
        position=9,
    )
    for answer in ("very", "incredibly", "omggreen"):
        AnswerOptionFactory(question=question, answer=answer)
    return question


@pytest.fixture
def cfp_track(cfp_event):
    """A track for the CfP event, with use_tracks enabled."""
    cfp_event.feature_flags["use_tracks"] = True
    cfp_event.save()
    return TrackFactory(event=cfp_event, name="Test Track")


@pytest.fixture
def cfp_access_code(cfp_event):
    """A valid access code for the CfP event."""
    return SubmitterAccessCodeFactory(event=cfp_event)
