# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.fields import ColorField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.ui import generate_contrast_color
from pretalx.submission.domain.track import apply_track_field_changes
from pretalx.submission.models import Track


class TrackForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, event, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.instance.event = event
        if not self.instance._state.adding:
            url = f"{event.cfp.urls.new_access_code}?track={self.instance.pk}"
            self.fields["requires_access_code"].help_text += " " + _(
                'You can create an access code <a href="{url}">here</a>.'
            ).format(url=url)
        elif not self.is_bound and not self.initial.get("color"):
            existing = list(
                event.tracks.exclude(color="").values_list("color", flat=True)
            )
            self.initial["color"] = generate_contrast_color(existing_colors=existing)
        if not event.get_feature_flag("attendee_signup"):
            self.fields.pop("attendee_signup_required", None)

    def save(self, commit=True):
        changed_fields = list(self.changed_data)
        instance = super().save(commit=commit)
        self.signup_pinned_submissions = []
        if commit and not instance._state.adding:
            self.signup_pinned_submissions = apply_track_field_changes(
                instance, changed_fields
            )
        return instance

    class Meta:
        model = Track
        fields = (
            "name",
            "description",
            "color",
            "requires_access_code",
            "attendee_signup_required",
        )
        field_classes = {"color": ColorField}
