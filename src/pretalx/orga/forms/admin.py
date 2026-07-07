# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _
from hierarkey.forms import HierarkeyForm

from pretalx.common.models.settings import GlobalSettings


class GlobalSettingsForm(HierarkeyForm):
    def __init__(self, *args, **kwargs):
        self.obj = GlobalSettings()
        super().__init__(*args, obj=self.obj, attribute_name="settings", **kwargs)


class UpdateSettingsForm(GlobalSettingsForm):
    update_check_enabled = forms.BooleanField(
        required=False,
        label=_("Perform update checks"),
        help_text=_(
            "During the update check, pretalx will report a random (but stable) installation ID, "
            "the current version of pretalx and of your installed plugins, your Python version "
            "and database engine, and the number of events in your installation to servers "
            "operated by the pretalx developers. We use this information to decide which "
            "versions to support and which features and bug fixes to prioritise."
        ),
    )
    update_check_email = forms.EmailField(
        required=False,
        label=_("Email notifications"),
        help_text=_(
            "We will notify you at this address if we detect that a new update is available. This "
            "address will not be transmitted to pretalx.com, the emails will be sent by your server "
            "locally."
        ),
    )
