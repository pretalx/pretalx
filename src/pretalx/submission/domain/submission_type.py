# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction

from pretalx.submission.domain.submission import update_duration


def propagate_default_duration(submission_type):
    for submission in submission_type.submissions.filter(duration__isnull=True):
        update_duration(submission)


def can_delete_submission_type(submission_type) -> bool:
    if submission_type.event.cfp.default_type_id == submission_type.pk:
        return False
    return not submission_type.submissions.exists()


def make_default_submission_type(submission_type, *, person=None):
    cfp = submission_type.event.cfp
    if cfp.default_type_id == submission_type.pk:
        return
    with transaction.atomic():
        cfp.default_type = submission_type
        cfp.save(update_fields=["default_type"])
        submission_type.log_action(
            "pretalx.submission_type.make_default", person=person, orga=True
        )
