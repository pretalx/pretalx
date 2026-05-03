# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def create_feedback(feedback):
    if feedback.speaker is None:
        speakers = feedback.talk.speakers.all()
        if len(speakers) == 1:
            feedback.speaker = speakers[0]
    feedback.save()
    return feedback
