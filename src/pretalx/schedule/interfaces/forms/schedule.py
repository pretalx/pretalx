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
from pretalx.schedule.domain.release import guess_schedule_version
from pretalx.schedule.models import Schedule
from pretalx.schedule.validators.schedule import validate_unique_version


class ScheduleReleaseForm(PretalxI18nModelForm):
    default_renderer = InlineFormRenderer

    notify_speakers = forms.BooleanField(
        label=_("Notify speakers of changes"), required=False, initial=True
    )

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
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

    def clean_version(self):
        version = self.cleaned_data.get("version")
        validate_unique_version(
            version, event=self.event, exclude_schedule=self.instance
        )
        return version

    class Meta:
        model = Schedule
        fields = ("version", "comment")
