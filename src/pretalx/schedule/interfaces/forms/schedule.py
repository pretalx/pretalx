# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Louis Taylor

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.mixins import PretalxI18nModelForm
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.text.phrases import phrases
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.schedule.domain.release import (
    apply_signup_capacity_changes,
    guess_schedule_version,
)
from pretalx.schedule.models import Schedule
from pretalx.schedule.validators.schedule import validate_unique_version


class ScheduleReleaseForm(PretalxI18nModelForm):
    default_renderer = InlineFormRenderer

    notify_speakers = forms.BooleanField(
        label=_("Notify speakers of changes"), required=False, initial=True
    )

    def __init__(self, *args, event=None, warnings=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.warnings = warnings or {}
        self.fields["version"].required = True
        self.fields["comment"].widget.attrs["rows"] = 4
        url = mail_template_by_role(
            self.event, MailTemplateRoles.NEW_SCHEDULE
        ).urls.base
        self.fields[
            "notify_speakers"
        ].help_text = f"<a href='{url}'>{_('Email template')}</a>"
        if not self.event.current_schedule:
            self.fields["comment"].initial = phrases.schedule.first_schedule
        else:
            self.fields["comment"].initial = _("We released a new schedule version!")
        version_initial = self.fields["version"].initial or self.initial.get("version")
        if not version_initial:
            version_initial = guess_schedule_version(self.event)
        self.fields["version"].initial = version_initial
        self._build_expand_capacity_fields()

    def _build_expand_capacity_fields(self):
        self.expand_capacity_entries = []
        for entry in self.warnings.get("signup_room_too_large", []):
            submission = entry["submission"]
            field_name = f"expand_capacity_{submission.pk}"
            self.fields[field_name] = forms.BooleanField(
                label=_("Expand “{title}” capacity to {capacity}").format(
                    title=submission.title, capacity=entry["room_capacity"]
                ),
                required=False,
                initial=False,
            )
            self.expand_capacity_entries.append({"field_name": field_name, **entry})

    def get_expand_capacity_fields(self):
        return [
            {"bound_field": self[entry["field_name"]], **entry}
            for entry in self.expand_capacity_entries
        ]

    def apply_expand_capacity(self, user=None):
        updates = [
            (entry["submission"], entry["room_capacity"])
            for entry in self.expand_capacity_entries
            if self.cleaned_data.get(entry["field_name"])
        ]
        apply_signup_capacity_changes(self.event, updates, user=user)

    def clean_version(self):
        version = self.cleaned_data.get("version")
        validate_unique_version(
            version, event=self.event, exclude_schedule=self.instance
        )
        return version

    class Meta:
        model = Schedule
        fields = ("version", "comment")
