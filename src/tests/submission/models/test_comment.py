# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import SubmissionCommentFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_comment_str():
    comment = SubmissionCommentFactory()
    assert (
        str(comment)
        == f'Comment by {comment.user.get_display_name()} on "{comment.submission.title}"'
    )


def test_comment_event():
    comment = SubmissionCommentFactory()
    assert comment.event == comment.submission.event


def test_comment_log_prefix():
    comment = SubmissionCommentFactory()
    assert comment.log_prefix == "pretalx.submission.comment"


def test_comment_ordering():
    submission = SubmissionFactory()
    comment1 = SubmissionCommentFactory(submission=submission)
    comment2 = SubmissionCommentFactory(submission=submission)

    comments = list(submission.comments.all())

    assert comments == [comment1, comment2]


def test_comment_reply_to():
    submission = SubmissionFactory()
    parent = SubmissionCommentFactory(submission=submission)
    reply = SubmissionCommentFactory(submission=submission, reply_to=parent)

    replies = list(parent.replies.all())

    assert replies == [reply]
