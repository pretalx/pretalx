# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django_scopes.forms import SafeModelMultipleChoiceField

from pretalx.common.forms.fields import SizeFileField
from pretalx.common.forms.mixins import PretalxI18nModelForm
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.person.models import SpeakerInformation


class SpeakerInformationForm(PretalxI18nModelForm):
    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["limit_types"].queryset = event.submission_types.all()
        if event.has_active_tracks:
            self.fields["limit_tracks"].queryset = event.tracks.all()
        else:
            self.fields.pop("limit_tracks")

    class Meta:
        model = SpeakerInformation
        fields = (
            "title",
            "text",
            "target_group",
            "limit_types",
            "limit_tracks",
            "resource",
        )
        field_classes = {
            "limit_tracks": SafeModelMultipleChoiceField,
            "limit_types": SafeModelMultipleChoiceField,
            "resource": SizeFileField,
        }
        widgets = {
            "limit_tracks": EnhancedSelectMultiple(color_field="color"),
            "limit_types": EnhancedSelectMultiple,
        }
