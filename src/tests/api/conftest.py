import pytest
from django_scopes import scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS
from pretalx.submission.models import (
    AnswerOption,
    QuestionVariant,
    ReviewScore,
    ReviewScoreCategory,
    SubmissionStates,
)
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    AnswerFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserApiTokenFactory,
    UserFactory,
)
from tests.utils import make_orga_user

READ_ACTIONS = ["list", "retrieve"]
WRITE_ACTIONS = ["list", "retrieve", "create", "update", "destroy", "actions"]


@pytest.fixture
def orga_user(event):
    """An organiser user with full permissions for the event."""
    with scopes_disabled():
        return make_orga_user(
            event, can_change_submissions=True, can_change_event_settings=True
        )


@pytest.fixture
def orga_token(orga_user, event):
    """Read-only API token for the organiser (alias used by speaker/upload tests)."""
    token = UserApiTokenFactory(user=orga_user)
    token.events.add(event)
    token.endpoints = dict.fromkeys(ENDPOINTS, READ_ACTIONS)
    token.save()
    return token


@pytest.fixture
def orga_read_token(orga_user, event):
    """Read-only API token for the organiser."""
    token = UserApiTokenFactory(user=orga_user)
    token.events.add(event)
    token.endpoints = dict.fromkeys(ENDPOINTS, READ_ACTIONS)
    token.save()
    return token


@pytest.fixture
def orga_write_token(orga_user, event):
    """Read-write API token for the organiser."""
    token = UserApiTokenFactory(user=orga_user)
    token.events.add(event)
    token.endpoints = dict.fromkeys(ENDPOINTS, WRITE_ACTIONS)
    token.save()
    return token


@pytest.fixture
def review_token(review_user, event):
    """Read-write API token for the reviewer."""
    token = UserApiTokenFactory(user=review_user)
    token.events.add(event)
    token.endpoints = dict.fromkeys(ENDPOINTS, WRITE_ACTIONS)
    token.save()
    return token


@pytest.fixture
def other_review_user(event):
    """Another reviewer user for testing other-review scenarios."""
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(user)
    return user


@pytest.fixture
def other_event():
    """A separate event under a different organiser for cross-event tests."""
    from tests.factories import EventFactory  # noqa: PLC0415

    return EventFactory()


@pytest.fixture
def question(event):
    """A basic number question targeting submissions."""
    return QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
    )


@pytest.fixture
def choice_question(event):
    """A choice question with three options."""
    with scopes_disabled():
        q = QuestionFactory(
            event=event,
            variant=QuestionVariant.CHOICES,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
        )
        for answer_text in (
            "Original Option 1",
            "Original Option 2",
            "Original Option 3",
        ):
            AnswerOption.objects.create(question=q, answer=answer_text)
    return q


@pytest.fixture
def review_question(event):
    """A question targeting reviewers."""
    return QuestionFactory(
        event=event,
        variant=QuestionVariant.STRING,
        target="reviewer",
        question_required=QuestionRequired.REQUIRED,
    )


@pytest.fixture
def speaker_profile(submission):
    """The speaker profile on the submission fixture."""
    with scopes_disabled():
        return submission.speakers.first()


@pytest.fixture
def answer(submission, question):
    """An answer to the question fixture, attached to the submission."""
    return AnswerFactory(question=question, submission=submission, answer="42")


@pytest.fixture
def review(submission, review_user):
    """A review by review_user on the submission fixture."""
    return ReviewFactory(submission=submission, user=review_user, text="Looks great!")


@pytest.fixture
def other_review(other_submission, other_review_user):
    """A review by other_review_user on the other_submission."""
    return ReviewFactory(
        submission=other_submission, user=other_review_user, text="Looks horrible!"
    )


@pytest.fixture
def review_score_category(event):
    """A score category for the event."""
    return ReviewScoreCategory.objects.create(event=event, name="Impact", weight=1)


@pytest.fixture
def review_score_positive(review_score_category):
    """A positive review score value."""
    from decimal import Decimal  # noqa: PLC0415

    return ReviewScore.objects.create(
        category=review_score_category, value=Decimal("2.0"), label="Good"
    )


@pytest.fixture
def review_score_negative(review_score_category):
    """A negative review score value."""
    from decimal import Decimal  # noqa: PLC0415

    return ReviewScore.objects.create(
        category=review_score_category, value=Decimal("-1.0"), label="Bad"
    )


@pytest.fixture
def speaker_on_event(event):
    """A speaker on the event with a confirmed submission."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
    return speaker, sub
