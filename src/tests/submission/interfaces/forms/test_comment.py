# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.interfaces.forms import SubmissionCommentForm
from tests.factories import SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_comment_form_requires_text_and_saves_through_domain():
    submission = SubmissionFactory()
    user = UserFactory()

    form = SubmissionCommentForm(data={"text": ""}, submission=submission, user=user)

    assert form.errors == {"text": ["This field is required."]}

    form = SubmissionCommentForm(
        data={"text": "Needs more detail."}, submission=submission, user=user
    )
    assert form.is_valid(), form.errors

    comment = form.save()

    assert comment.pk is not None
    assert comment.submission == submission
    assert comment.user == user
    assert comment.text == "Needs more detail."
    assert comment.logged_actions().count() == 1
