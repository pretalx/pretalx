import pytest
from django_scopes import scopes_disabled

from tests.factories import SubmissionCommentFactory, SubmissionFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_comment_str():
    comment = SubmissionCommentFactory()
    assert (
        str(comment)
        == f'Comment by {comment.user.get_display_name()} on "{comment.submission.title}"'
    )


@pytest.mark.django_db
def test_comment_event():
    comment = SubmissionCommentFactory()
    assert comment.event == comment.submission.event


@pytest.mark.django_db
def test_comment_log_prefix():
    comment = SubmissionCommentFactory()
    assert comment.log_prefix == "pretalx.submission.comment"


@pytest.mark.django_db
def test_comment_ordering():
    submission = SubmissionFactory()
    comment1 = SubmissionCommentFactory(submission=submission)
    comment2 = SubmissionCommentFactory(submission=submission)

    with scopes_disabled():
        comments = list(submission.comments.all())

    assert comments == [comment1, comment2]


@pytest.mark.django_db
def test_comment_reply_to():
    submission = SubmissionFactory()
    parent = SubmissionCommentFactory(submission=submission)
    reply = SubmissionCommentFactory(submission=submission, reply_to=parent)

    with scopes_disabled():
        replies = list(parent.replies.all())

    assert replies == [reply]
