# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.widgets import HtmlDateTimeInput, TextInputWithAddon
from pretalx.submission.domain.submission_type import propagate_default_duration
from pretalx.submission.models import SubmissionType


class SubmissionTypeForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, event, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.instance.event = event
        if not event.get_feature_flag("attendee_signup"):
            self.fields.pop("attendee_signup_required", None)

    def save(self, commit=True):
        duration_changed = "default_duration" in self.changed_data
        instance = super().save(commit=commit)
        if commit and duration_changed:
            propagate_default_duration(instance)
        return instance

    class Meta:
        model = SubmissionType
        fields = (
            "name",
            "default_duration",
            "deadline",
            "requires_access_code",
            "attendee_signup_required",
        )
        widgets = {
            "deadline": HtmlDateTimeInput,
            "default_duration": TextInputWithAddon(addon_after=_("minutes")),
        }
