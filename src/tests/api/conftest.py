# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.person.models.auth_token import ENDPOINTS
from pretalx.submission.models import QuestionVariant
from pretalx.submission.models.question import QuestionRequired
from tests.factories import AnswerOptionFactory, QuestionFactory, UserApiTokenFactory
from tests.utils import make_orga_user

READ_ACTIONS = ["list", "retrieve"]
WRITE_ACTIONS = ["list", "retrieve", "create", "update", "destroy", "actions"]


@pytest.fixture
def orga_user(event):
    """An organiser user with full permissions for the event."""
    return make_orga_user(
        event, can_change_submissions=True, can_change_event_settings=True
    )


@pytest.fixture
def orga_read_token(orga_user, event):
    """Read-only API token for the organiser."""
    return UserApiTokenFactory(
        user=orga_user, events=[event], endpoints=dict.fromkeys(ENDPOINTS, READ_ACTIONS)
    )


@pytest.fixture
def orga_write_token(orga_user, event):
    """Read-write API token for the organiser."""
    return UserApiTokenFactory(
        user=orga_user,
        events=[event],
        endpoints=dict.fromkeys(ENDPOINTS, WRITE_ACTIONS),
    )


@pytest.fixture
def review_token(review_user, event):
    """Read-write API token for the reviewer."""
    return UserApiTokenFactory(
        user=review_user,
        events=[event],
        endpoints=dict.fromkeys(ENDPOINTS, WRITE_ACTIONS),
    )


@pytest.fixture
def choice_question(event):
    """A choice question with three options."""
    q = QuestionFactory(
        event=event,
        variant=QuestionVariant.CHOICES,
        target="speaker",
        question_required=QuestionRequired.OPTIONAL,
    )
    for answer_text in ("Original Option 1", "Original Option 2", "Original Option 3"):
        AnswerOptionFactory(question=q, answer=answer_text)
    return q
