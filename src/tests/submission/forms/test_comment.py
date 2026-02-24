import pytest
from django_scopes import scopes_disabled

from pretalx.submission.forms.comment import SubmissionCommentForm
from tests.factories import SubmissionFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("text", "expected_valid"), (("This looks great!", True), ("", False))
)
def test_comment_form_validates_text_field(text, expected_valid):
    with scopes_disabled():
        submission = SubmissionFactory()
        user = UserFactory()

    form = SubmissionCommentForm(data={"text": text}, submission=submission, user=user)

    assert form.is_valid() == expected_valid
    if not expected_valid:
        assert "text" in form.errors


@pytest.mark.django_db
def test_comment_form_save_creates_comment():
    with scopes_disabled():
        submission = SubmissionFactory()
        user = UserFactory()

    form = SubmissionCommentForm(
        data={"text": "Needs more detail."}, submission=submission, user=user
    )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        comment = form.save()

    assert comment.pk is not None
    assert comment.submission == submission
    assert comment.user == user
    assert comment.text == "Needs more detail."


@pytest.mark.django_db
def test_comment_form_save_logs_action():
    with scopes_disabled():
        submission = SubmissionFactory()
        user = UserFactory()

    form = SubmissionCommentForm(
        data={"text": "Logging test"}, submission=submission, user=user
    )
    assert form.is_valid(), form.errors

    with scopes_disabled():
        comment = form.save()
        log_entry = comment.logged_actions().first()

    assert log_entry.action_type == "pretalx.submission.comment.create"
    assert log_entry.person == user
