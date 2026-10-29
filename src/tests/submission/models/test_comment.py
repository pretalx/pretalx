# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import SubmissionCommentFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_comment_thread():
    submission = SubmissionFactory()
    comment1 = SubmissionCommentFactory(submission=submission)
    comment2 = SubmissionCommentFactory(submission=submission, reply_to=comment1)

    assert (
        str(comment1)
        == f'Comment by {comment1.user.get_display_name()} on "{submission.title}"'
    )
    assert comment1.event == submission.event
    assert list(submission.comments.all()) == [comment1, comment2]
    assert list(comment1.replies.all()) == [comment2]
