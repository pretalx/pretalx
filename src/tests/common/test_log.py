# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils.html import escape

from pretalx.common.log import (
    LOG_ALIASES,
    LOG_NAMES,
    _submission_label_text,
    compute_log_changes,
    default_activitylog_display,
    default_activitylog_object_link,
    resolve_log_changes,
)
from pretalx.common.models.log import ActivityLog
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    ActivityLogFactory,
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
    log = ActivityLog(action_type="pretalx.event.delete", data={"name": "Test Event"})

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.event.delete"]


def test_default_activitylog_display_template_with_non_dict_data():
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
    submission = SubmissionFactory(state=state)
    log = ActivityLog(content_object=submission)

    result = default_activitylog_object_link(sender=submission.event, activitylog=log)

    assert result == (
        f'{expected_label} <a href="{submission.orga_urls.base}">'
        f"{escape(submission.title)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_submission_comment():
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
    question = QuestionFactory()
    log = ActivityLog(content_object=question)

    result = default_activitylog_object_link(sender=question.event, activitylog=log)

    assert result == (
        f'Custom field <a href="{question.urls.base}">{escape(question.question)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_option():
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
    event = EventFactory()
    cfp = event.cfp
    log = ActivityLog(content_object=cfp)

    result = default_activitylog_object_link(sender=event, activitylog=log)

    assert result == f'<a href="{cfp.urls.text}">Call for Proposals</a>'


@pytest.mark.django_db
def test_default_activitylog_object_link_mail_template():
    template = MailTemplateFactory()
    log = ActivityLog(content_object=template)

    result = default_activitylog_object_link(sender=template.event, activitylog=log)

    assert result == (
        f'Email template <a href="{template.urls.base}">{escape(template.subject)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_queued_mail():
    mail = QueuedMailFactory()
    log = ActivityLog(content_object=mail)

    result = default_activitylog_object_link(sender=mail.event, activitylog=log)

    assert result == (f'Email <a href="{mail.urls.base}">{escape(mail.subject)}</a>')


@pytest.mark.django_db
def test_default_activitylog_object_link_speaker_profile():
    speaker = SpeakerFactory()
    log = ActivityLog(content_object=speaker)

    result = default_activitylog_object_link(sender=speaker.event, activitylog=log)

    assert result == (
        f'Speaker <a href="{speaker.orga_urls.base}">'
        f"{escape(speaker.user.get_display_name())}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_event():
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
    track = TrackFactory()
    log = ActivityLog(content_object=track)

    result = default_activitylog_object_link(sender=track.event, activitylog=log)

    assert result is None


def test_compute_log_changes_both_none():
    assert compute_log_changes(None, None) == {}


def test_compute_log_changes_identical_truthy_values():
    data = {"title": "Same Title", "state": "submitted"}

    assert compute_log_changes(data, data) == {}


def test_compute_log_changes_ignores_both_falsy():
    """When both old and new are falsy (empty string and None), the key is
    skipped."""
    assert compute_log_changes({"key": ""}, {"key": None}) == {}


def test_compute_log_changes_mixed_keys():
    """Changed, unchanged, and None-to-truthy keys are handled correctly in a
    single call."""
    old_data = {"title": "Old Title", "state": "submitted", "track": None}
    new_data = {"title": "New Title", "state": "submitted", "track": 1}

    changes = compute_log_changes(old_data, new_data)

    assert changes["title"] == {"old": "Old Title", "new": "New Title"}
    assert "state" not in changes
    assert changes["track"] == {"old": None, "new": 1}


def test_compute_log_changes_tracks_additions():
    assert compute_log_changes({}, {"title": "New"}) == {
        "title": {"old": None, "new": "New"}
    }


def test_compute_log_changes_tracks_removals():
    assert compute_log_changes({"title": "Old"}, {}) == {
        "title": {"old": "Old", "new": None}
    }


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_without_data():
    log = ActivityLogFactory(data=None)

    assert resolve_log_changes(log) is None


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_without_event():
    log = ActivityLogFactory(
        event=None, data={"changes": {"title": {"old": "A", "new": "B"}}}
    )

    assert resolve_log_changes(log) is None


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_without_changes_key():
    log = ActivityLogFactory(data={"some_key": "some_value"})

    assert resolve_log_changes(log) is None


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_when_content_object_deleted():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "A", "new": "B"}}},
    )
    submission.delete()

    assert resolve_log_changes(log) is None
