# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.interfaces.forms import SubmissionCommentForm
from tests.factories import SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("text", "expected_valid"), (("This looks great!", True), ("", False))
)
def test_comment_form_validates_text_field(text, expected_valid):
    submission = SubmissionFactory()
    user = UserFactory()

    form = SubmissionCommentForm(data={"text": text}, submission=submission, user=user)

    assert form.is_valid() == expected_valid
    if not expected_valid:
        assert "text" in form.errors


def test_comment_form_save_delegates_to_submission():
    submission = SubmissionFactory()
    user = UserFactory()

    form = SubmissionCommentForm(
        data={"text": "Needs more detail."}, submission=submission, user=user
    )
    assert form.is_valid(), form.errors

    comment = form.save()

    assert comment.pk is not None
    assert comment.submission == submission
    assert comment.user == user
    assert comment.text == "Needs more detail."
