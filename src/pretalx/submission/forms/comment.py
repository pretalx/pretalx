# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.submission.models import SubmissionComment


class SubmissionCommentForm(forms.ModelForm):
    default_renderer = InlineFormRenderer

    class Meta:
        model = SubmissionComment
        fields = ("text",)

    def __init__(self, *args, submission=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.submission = submission
        self.user = user

    def save(self, *args, **kwargs):
        self.instance.submission = self.submission
        self.instance.user = self.user
        instance = super().save(*args, **kwargs)
        instance.log_action(
            "pretalx.submission.comment.create", person=self.user, orga=True
        )
        return instance
