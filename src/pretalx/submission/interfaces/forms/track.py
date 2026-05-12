# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.fields import ColorField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.submission.models import Track


class TrackForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, event, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.instance.event = event
        if self.instance.pk:
            url = f"{event.cfp.urls.new_access_code}?track={self.instance.pk}"
            self.fields["requires_access_code"].help_text += " " + _(
                'You can create an access code <a href="{url}">here</a>.'
            ).format(url=url)

    class Meta:
        model = Track
        fields = ("name", "description", "color", "requires_access_code")
        field_classes = {"color": ColorField}
