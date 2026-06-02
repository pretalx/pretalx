# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.cfp.forms import CfPFormMixin, RequestRequire
from pretalx.common.forms.fields import AvailabilitiesField, ProfilePictureField
from pretalx.common.forms.mixins import ReadOnlyFlag
from pretalx.person.domain.profile import apply_speaker_profile_changes
from pretalx.person.domain.queries.profile import other_speaker_profiles
from pretalx.person.interfaces.forms.widgets import BiographyWidget
from pretalx.person.models import SpeakerProfile, User
from pretalx.person.validators import validate_email_unique


class SpeakerProfileForm(CfPFormMixin, ReadOnlyFlag, RequestRequire, forms.ModelForm):
    availabilities = AvailabilitiesField()
    avatar = ProfilePictureField()

    def __init__(
        self,
        *args,
        user,
        event,
        name=None,
        with_email=True,
        essential_only=False,
        is_orga=False,
        **kwargs,
    ):
        self.user = user
        self.event = event
        self.essential_only = essential_only
        self.is_orga = is_orga
        self._show_email = with_email and user is not None and not essential_only

        kwargs["instance"] = user.get_speaker(event) if user else None
        initial = kwargs.get("initial", {})
        super().__init__(*args, **kwargs)

        if self.event and "availabilities" in self.fields:
            self.fields["availabilities"].event = self.event
            self.fields["availabilities"].instance = self.instance
            self.fields["availabilities"].set_initial_from_instance()
            self.initial["availabilities"] = self.fields["availabilities"].initial

        if self.instance and self.instance.name:
            name_initial = self.instance.name
        else:
            name_initial = name or (self.user.name if self.user else None)
        name_field = User._meta.get_field("name")
        self.fields["name"] = name_field.formfield(
            initial=name_initial,
            disabled=self.read_only,
            help_text=name_field.help_text,
        )
        self._update_cfp_texts("name")

        if self._show_email:
            email_field = User._meta.get_field("email")
            self.fields["email"] = email_field.formfield(
                initial=initial.get("email", self.user.email),
                disabled=self.read_only,
                help_text=email_field.help_text,
            )
            self._update_cfp_texts("email")

        if "avatar" in self.fields:
            current_picture = (
                self.instance.profile_picture
                if self.instance and not self.instance._state.adding
                else None
            )
            self.fields["avatar"].user = self.user
            self.fields["avatar"].current_picture = current_picture
            self.fields["avatar"].upload_only = self.is_orga
            self.fields["avatar"].set_widget_data()

        if self.field_configuration:
            field_order = [
                field_data["key"] for field_data in self.field_configuration.values()
            ]
            self._reorder_fields(field_order)

        if (
            "biography" in self.fields
            and self.user
            and not self.is_orga
            and not self.read_only
            and not getattr(self.instance, "biography", None)
        ):
            suggestions = list(
                other_speaker_profiles(self.instance)
                .exclude(biography="")
                .exclude(biography__isnull=True)
                .values_list("pk", "event__name", "biography")
            )
            if suggestions:
                self.fields["biography"].widget = BiographyWidget(
                    suggestions=[
                        {"id": pk, "event_name": event_name, "biography": bio}
                        for pk, event_name, bio in suggestions
                    ]
                )

        if not self.is_orga:
            self.fields.pop("internal_notes", None)

        if self.is_bound and not self.is_valid() and "availabilities" in self.errors:
            self.data = self.data.copy()
            self.data["availabilities"] = self.initial["availabilities"]

    def clean(self):
        data = super().clean()
        if email := data.get("email"):
            validate_email_unique(email, exclude_user=self.user)
        return data

    def save(self, **kwargs):
        self.instance.name = self.cleaned_data["name"]
        super().save(**kwargs)
        if "avatar" in self.fields:
            self.fields["avatar"].save(
                self.instance, self.user, self.cleaned_data.get("avatar")
            )
        if "availabilities" in self.fields:
            self.fields["availabilities"].save(
                self.instance, self.cleaned_data.get("availabilities")
            )
        apply_speaker_profile_changes(
            self.instance, self.changed_data, new_email=self.cleaned_data.get("email")
        )
        return self.instance

    class Meta:
        model = SpeakerProfile
        fields = ("biography", "internal_notes")
        public_fields = ["name", "biography", "avatar"]
        request_require = {"avatar", "biography", "availabilities"}


class SpeakerAvailabilityForm(forms.Form):
    """Pre-confirmation availability prompt; the rest of the speaker profile
    is edited via :class:`SpeakerProfileForm`."""

    def __init__(self, *args, event=None, speaker=None, **kwargs):
        self.event = event
        self.speaker = speaker
        super().__init__(*args, **kwargs)

        if self.event and self.speaker and self.event.cfp.request_availabilities:
            self.fields["availabilities"] = AvailabilitiesField(
                event=self.event,
                instance=self.speaker,
                required=self.event.cfp.require_availabilities,
            )

    def save(self):
        if (
            not getattr(self, "cleaned_data", None)
            or "availabilities" not in self.fields
        ):
            return None
        self.fields["availabilities"].save(
            self.speaker, self.cleaned_data.get("availabilities")
        )
        return self.speaker


class OrgaProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "locale")


__all__ = ["OrgaProfileForm", "SpeakerAvailabilityForm", "SpeakerProfileForm"]
