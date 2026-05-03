# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.domain.comment import create_comment
from pretalx.submission.models import SubmissionComment
from tests.factories import SubmissionCommentFactory, SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_comment_persists_fields():
    submission = SubmissionFactory()
    user = UserFactory()

    comment = create_comment(
        SubmissionComment(submission=submission, user=user, text="Hello.")
    )

    assert comment.pk is not None
    assert comment.submission == submission
    assert comment.user == user
    assert comment.text == "Hello."
    assert comment.reply_to is None


def test_create_comment_with_reply_to():
    submission = SubmissionFactory()
    user = UserFactory()
    parent = SubmissionCommentFactory(submission=submission)

    comment = create_comment(
        SubmissionComment(
            submission=submission, user=user, text="Reply", reply_to=parent
        )
    )

    assert comment.reply_to == parent


def test_create_comment_logs_action():
    submission = SubmissionFactory()
    user = UserFactory()

    comment = create_comment(
        SubmissionComment(submission=submission, user=user, text="Logging test")
    )
    log_entries = list(comment.logged_actions())

    assert len(log_entries) == 1
    assert log_entries[0].action_type == "pretalx.submission.comment.create"
    assert log_entries[0].person == user
