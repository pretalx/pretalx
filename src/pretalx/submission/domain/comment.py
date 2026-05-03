# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def create_comment(comment):
    comment.save()
    comment.log_action(
        "pretalx.submission.comment.create", person=comment.user, orga=True
    )
    return comment
