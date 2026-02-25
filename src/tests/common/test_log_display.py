import pytest
from django.utils.html import escape
from django_scopes import scopes_disabled

from pretalx.common.log_display import (
    LOG_ALIASES,
    LOG_NAMES,
    _submission_label_text,
    default_activitylog_display,
    default_activitylog_object_link,
)
from pretalx.common.models.log import ActivityLog
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    MailTemplateFactory,
    QuestionFactory,
    QueuedMailFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = pytest.mark.unit


def test_default_activitylog_display_known_action_type():
    log = ActivityLog(action_type="pretalx.submission.create")

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.submission.create"]


def test_default_activitylog_display_template_with_valid_data():
    log = ActivityLog(
        action_type="pretalx.event.delete",
        data={"name": "Test Event", "slug": "test", "organiser": "Org"},
    )

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == "The event Test Event (test) by Org was deleted."


def test_default_activitylog_display_template_with_missing_data():
    """When template data is incomplete, falls through to LOG_NAMES."""
    log = ActivityLog(action_type="pretalx.event.delete", data={"name": "Test Event"})

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.event.delete"]


def test_default_activitylog_display_template_with_non_dict_data():
    """When data is not a dict, falls through to LOG_NAMES."""
    log = ActivityLog(action_type="pretalx.event.delete", data=None)

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.event.delete"]


@pytest.mark.parametrize(("alias", "resolved"), tuple(LOG_ALIASES.items()))
def test_default_activitylog_display_alias_resolves(alias, resolved):
    log = ActivityLog(action_type=alias)

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES[resolved]


def test_default_activitylog_display_unknown_action_type_returns_none():
    log = ActivityLog(action_type="pretalx.totally.unknown.action")

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result is None


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (SubmissionStates.ACCEPTED, "Session"),
        (SubmissionStates.CONFIRMED, "Session"),
        (SubmissionStates.SUBMITTED, "Proposal"),
        (SubmissionStates.REJECTED, "Proposal"),
        (SubmissionStates.CANCELED, "Proposal"),
        (SubmissionStates.WITHDRAWN, "Proposal"),
        (SubmissionStates.DRAFT, "Proposal"),
    ),
)
def test_submission_label_text_by_state(state, expected):
    submission = Submission(state=state)

    result = str(_submission_label_text(submission))

    assert result == expected


def test_default_activitylog_object_link_no_content_object_returns_none():
    log = ActivityLog()

    result = default_activitylog_object_link(sender=None, activitylog=log)

    assert result is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "expected_label"),
    ((SubmissionStates.ACCEPTED, "Session"), (SubmissionStates.SUBMITTED, "Proposal")),
)
def test_default_activitylog_object_link_submission(state, expected_label):
    with scopes_disabled():
        submission = SubmissionFactory(state=state)
    log = ActivityLog(content_object=submission)

    result = default_activitylog_object_link(sender=submission.event, activitylog=log)

    assert result == (
        f'{expected_label} <a href="{submission.orga_urls.base}">'
        f"{escape(submission.title)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_submission_comment():
    with scopes_disabled():
        comment = SubmissionCommentFactory()
    log = ActivityLog(content_object=comment)

    result = default_activitylog_object_link(
        sender=comment.submission.event, activitylog=log
    )

    url = f"{comment.submission.orga_urls.comments}#comment-{comment.pk}"
    assert result == (
        f'Proposal <a href="{url}">{escape(comment.submission.title)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_review():
    with scopes_disabled():
        review = ReviewFactory()
    log = ActivityLog(content_object=review)

    result = default_activitylog_object_link(
        sender=review.submission.event, activitylog=log
    )

    assert result == (
        f'Proposal <a href="{review.submission.orga_urls.reviews}">'
        f"{escape(review.submission.title)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_question():
    with scopes_disabled():
        question = QuestionFactory()
    log = ActivityLog(content_object=question)

    result = default_activitylog_object_link(sender=question.event, activitylog=log)

    assert result == (
        f'Custom field <a href="{question.urls.base}">{escape(question.question)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_option():
    with scopes_disabled():
        option = AnswerOptionFactory()
    log = ActivityLog(content_object=option)

    result = default_activitylog_object_link(
        sender=option.question.event, activitylog=log
    )

    assert result == (
        f'Custom field <a href="{option.question.urls.base}">'
        f"{escape(option.question.question)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_with_submission():
    with scopes_disabled():
        answer = AnswerFactory()
    log = ActivityLog(content_object=answer)

    result = default_activitylog_object_link(
        sender=answer.question.event, activitylog=log
    )

    assert result == (
        f'Response to custom field <a href="{answer.submission.orga_urls.base}">'
        f"{escape(answer.question.question)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_without_submission():
    with scopes_disabled():
        answer = AnswerFactory(submission=None)
    log = ActivityLog(content_object=answer)

    result = default_activitylog_object_link(
        sender=answer.question.event, activitylog=log
    )

    assert result == (
        f'Response to custom field <a href="{answer.question.urls.base}">'
        f"{escape(answer.question.question)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_cfp():
    with scopes_disabled():
        event = EventFactory()
    cfp = event.cfp
    log = ActivityLog(content_object=cfp)

    result = default_activitylog_object_link(sender=event, activitylog=log)

    assert result == f'<a href="{cfp.urls.text}">Call for Proposals</a>'


@pytest.mark.django_db
def test_default_activitylog_object_link_mail_template():
    with scopes_disabled():
        template = MailTemplateFactory()
    log = ActivityLog(content_object=template)

    result = default_activitylog_object_link(sender=template.event, activitylog=log)

    assert result == (
        f'Mail template <a href="{template.urls.base}">{escape(template.subject)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_queued_mail():
    with scopes_disabled():
        mail = QueuedMailFactory()
    log = ActivityLog(content_object=mail)

    result = default_activitylog_object_link(sender=mail.event, activitylog=log)

    assert result == (f'Email <a href="{mail.urls.base}">{escape(mail.subject)}</a>')


@pytest.mark.django_db
def test_default_activitylog_object_link_speaker_profile():
    with scopes_disabled():
        speaker = SpeakerFactory()
    log = ActivityLog(content_object=speaker)

    result = default_activitylog_object_link(sender=speaker.event, activitylog=log)

    assert result == (
        f'Speaker <a href="{speaker.orga_urls.base}">'
        f"{escape(speaker.user.get_display_name())}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_event():
    with scopes_disabled():
        event = EventFactory()
    log = ActivityLog(content_object=event)

    result = default_activitylog_object_link(sender=event, activitylog=log)

    assert result == (
        f'Event <a href="{event.orga_urls.base}">{escape(str(event.name))}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_unhandled_type_returns_none():
    """A content_object whose type is not in the isinstance chain
    (e.g. Track) should result in None."""
    with scopes_disabled():
        track = TrackFactory()
    log = ActivityLog(content_object=track)

    result = default_activitylog_object_link(sender=track.event, activitylog=log)

    assert result is None
