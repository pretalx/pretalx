# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled
from django_scopes.forms import SafeModelMultipleChoiceField

from pretalx.common.forms.fields import MultiEmailField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.event.interfaces.validators.team import (
    validate_team_event_coverage,
    validate_team_has_permission,
)
from pretalx.event.models import Organiser, Team
from pretalx.submission.models import Track


class TeamForm(ReadOnlyFlag, PretalxI18nModelForm):
    @scopes_disabled()
    def __init__(self, *args, organiser=None, instance=None, **kwargs):
        self.organiser = organiser
        super().__init__(*args, instance=instance, **kwargs)
        is_updating = instance and getattr(instance, "pk", None)
        if is_updating:
            self.fields["limit_events"].queryset = instance.organiser.events.all()
        else:
            self.fields["limit_events"].queryset = organiser.events.all()
        if is_updating and not instance.all_events and instance.limit_events.count():
            self.fields["limit_tracks"].queryset = Track.objects.filter(
                event__in=instance.limit_events.all()
            )
        else:
            self.fields["limit_tracks"].queryset = Track.objects.filter(
                event__organiser=organiser
            ).order_by("-event__date_from", "name")

    @scopes_disabled()
    def save(self, *args, **kwargs):
        self.instance.organiser = self.organiser
        return super().save(*args, **kwargs)

    def clean(self):
        data = super().clean()
        try:
            validate_team_event_coverage(
                all_events=data.get("all_events"), limit_events=data.get("limit_events")
            )
        except DjangoValidationError as exc:
            self.add_error("limit_events", exc.message_dict["limit_events"])
        try:
            validate_team_has_permission(data)
        except DjangoValidationError as exc:
            self.add_error(None, exc)
        return data

    class Media:
        js = [forms.Script("orga/js/forms/team.js", defer="")]

    class Meta:
        model = Team
        fields = [
            "name",
            "all_events",
            "limit_events",
            "can_create_events",
            "can_change_teams",
            "can_change_organiser_settings",
            "can_change_event_settings",
            "can_change_submissions",
            "is_reviewer",
            "force_hide_speaker_names",
            "limit_tracks",
        ]
        widgets = {
            "limit_events": EnhancedSelectMultiple,
            "limit_tracks": EnhancedSelectMultiple(color_field="color"),
        }
        field_classes = {"limit_tracks": SafeModelMultipleChoiceField}


class TeamInviteForm(ReadOnlyFlag, forms.Form):
    default_renderer = InlineFormRenderer

    emails = MultiEmailField(label=_("Email addresses"))


class OrganiserForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, **kwargs):
        kwargs["locales"] = "en"
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        if kwargs.get("instance"):
            self.fields["slug"].disabled = True

    class Meta:
        model = Organiser
        fields = ("name", "slug")
