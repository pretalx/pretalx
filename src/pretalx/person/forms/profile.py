# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField

from pretalx.cfp.forms.cfp import CfPFormMixin
from pretalx.common.forms.fields import (
    AvailabilitiesField,
    ProfilePictureField,
    SizeFileField,
)
from pretalx.common.forms.mixins import (
    PretalxI18nModelForm,
    ReadOnlyFlag,
    RequestRequire,
)
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import (
    BiographyWidget,
    EnhancedSelect,
    EnhancedSelectMultiple,
)
from pretalx.common.text.phrases import phrases
from pretalx.event.models import Event
from pretalx.person.models import SpeakerInformation, SpeakerProfile, User
from pretalx.schedule.models import Availability
from pretalx.submission.models import Question
from pretalx.submission.models.submission import SubmissionStates


def get_email_address_error():
    return (
        _("There already exists an account for this email address.")
        + " "
        + _("Please choose a different email address.")
    )


class SpeakerProfileForm(CfPFormMixin, ReadOnlyFlag, RequestRequire, forms.ModelForm):
    USER_FIELDS = ["email"]
    FIRST_TIME_EXCLUDE = ["email"]

    availabilities = AvailabilitiesField()
    avatar = ProfilePictureField()

    def __init__(self, *args, name=None, **kwargs):
        self.user = kwargs.pop("user", None)
        self.event = kwargs.pop("event", None)
        self.with_email = kwargs.pop("with_email", True)
        self.essential_only = kwargs.pop("essential_only", False)
        self.is_orga = kwargs.pop("is_orga", False)
        kwargs["instance"] = None
        if self.user:
            kwargs["instance"] = self.user.get_speaker(self.event)
        super().__init__(*args, **kwargs)

        if self.event and "availabilities" in self.fields:
            self.fields["availabilities"].event = self.event
            self.fields["availabilities"].instance = kwargs.get("instance")
            self.fields["availabilities"].set_initial_from_instance()
            if self.fields["availabilities"].initial:
                self.initial["availabilities"] = self.fields["availabilities"].initial
        read_only = kwargs.get("read_only", False)
        initial = kwargs.get("initial", {})

        # Name: use existing profile name, fall back to user.name for new profiles
        if self.instance and self.instance.name:
            name_initial = self.instance.name
        else:
            name_initial = name or (self.user.name if self.user else None)
        self.fields["name"] = User._meta.get_field("name").formfield(
            initial=name_initial,
            disabled=read_only,
            help_text=User._meta.get_field("name").help_text,
        )
        self._update_cfp_texts("name")

        if self.user:
            initial.update(
                {field: getattr(self.user, field) for field in self.user_fields}
            )
        for field in self.user_fields:
            field_class = User._meta.get_field(field).formfield
            self.fields[field] = field_class(
                initial=initial.get(field),
                disabled=read_only,
                help_text=User._meta.get_field(field).help_text,
            )
            self._update_cfp_texts(field)

        if "avatar" in self.fields:
            current_picture = (
                self.instance.profile_picture
                if self.instance and self.instance.pk
                else None
            )
            self.fields["avatar"].user = self.user
            self.fields["avatar"].current_picture = current_picture
            self.fields["avatar"].upload_only = self.is_orga
            self.fields["avatar"].set_widget_data()

        # Re-apply field ordering now that user fields have been added
        if self.field_configuration:
            field_order = [
                field_data["key"] for field_data in self.field_configuration.values()
            ]
            self._reorder_fields(field_order)

        if (
            "biography" in self.fields
            and self.user
            and not self.is_orga
            and not getattr(self.instance, "biography", None)
        ):
            with scopes_disabled():
                other_bios = list(
                    SpeakerProfile.objects.filter(user=self.user)
                    .exclude(event=self.event)
                    .exclude(biography="")
                    .exclude(biography__isnull=True)
                    .values_list("pk", "event__name", "biography")
                )
            if other_bios:
                suggestions = [
                    {"id": pk, "event_name": name, "biography": bio}
                    for pk, name, bio in other_bios
                ]
                self.fields["biography"].widget = BiographyWidget(
                    suggestions=suggestions
                )

        if not self.is_orga:
            self.fields.pop("internal_notes", None)

        if self.is_bound and not self.is_valid() and "availabilities" in self.errors:
            self.data = self.data.copy()
            if "availabilities" in self.initial:
                self.data["availabilities"] = self.initial["availabilities"]

    @cached_property
    def user_fields(self):
        if self.user and not self.essential_only:
            return [
                field
                for field in self.USER_FIELDS
                if field != "email" or self.with_email
            ]
        return [
            field
            for field in self.USER_FIELDS
            if field not in self.FIRST_TIME_EXCLUDE
            and (field != "email" or self.with_email)
        ]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        qs = User.objects.all()
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.filter(email__iexact=email):
            raise ValidationError(get_email_address_error())
        return email

    def save(self, **kwargs):
        for user_attribute in self.user_fields:
            value = self.cleaned_data.get(user_attribute)
            setattr(self.user, user_attribute, value)
            self.user.save(update_fields=[user_attribute])

        if "name" in self.cleaned_data:
            self.instance.name = self.cleaned_data["name"]
            # Sync to user.name only if user has no name yet
            if self.user and not self.user.name:
                self.user.name = self.cleaned_data["name"]
                self.user.save(update_fields=["name"])
        self.instance.event = self.event
        self.instance.user = self.user

        result = super().save(**kwargs)

        if "avatar" in self.fields:
            self.fields["avatar"].save(self.instance, self.user)

        availabilities = self.cleaned_data.get("availabilities")
        if availabilities is not None:
            Availability.replace_for_instance(self.instance, availabilities)

        return result

    class Meta:
        model = SpeakerProfile
        fields = ("biography", "internal_notes")
        public_fields = ["name", "biography", "avatar"]
        request_require = {"avatar", "biography", "availabilities"}


class SpeakerAvailabilityForm(forms.Form):
    """Form for handling speaker availability during submission confirmation."""

    def __init__(self, *args, event=None, speaker=None, **kwargs):
        self.event = event
        self.speaker = speaker
        super().__init__(*args, **kwargs)

        if self.event and self.speaker:
            self.fields["availabilities"] = AvailabilitiesField(
                event=self.event, instance=self.speaker
            )

    def save(self):
        if not hasattr(self, "cleaned_data"):
            return None

        availabilities = self.cleaned_data.get("availabilities")
        if availabilities is not None and self.speaker:
            Availability.replace_for_instance(self.speaker, availabilities)
        return self.speaker


class OrgaProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "locale")


class SpeakerInformationForm(PretalxI18nModelForm):
    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.fields["limit_types"].queryset = event.submission_types.all()
        if not event.get_feature_flag("use_tracks"):
            self.fields.pop("limit_tracks")
        else:
            self.fields["limit_tracks"].queryset = event.tracks.all()

    def save(self, *args, **kwargs):
        self.instance.event = self.event
        return super().save(*args, **kwargs)

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


class SpeakerFilterForm(forms.Form):
    default_renderer = InlineFormRenderer

    role = forms.ChoiceField(
        choices=(
            ("", _("Submitters and speakers")),
            ("true", phrases.schedule.speakers),
            ("false", _("Non-accepted submitters")),
        ),
        required=False,
        widget=EnhancedSelect,
    )
    arrived = forms.ChoiceField(
        choices=(
            ("", _("Any arrival status")),
            ("true", _("Marked as arrived")),
            ("false", _("Not yet arrived")),
        ),
        required=False,
        widget=EnhancedSelect,
    )
    fulltext = forms.BooleanField(required=False, label=_("Full text search"))
    question = SafeModelChoiceField(
        queryset=Question.objects.none(), required=False, widget=forms.HiddenInput()
    )

    def __init__(self, *args, event=None, filter_arrival=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.fields["question"].queryset = event.questions.all()
        if not filter_arrival:
            self.fields.pop("arrived")

    def filter_queryset(self, queryset):
        data = self.cleaned_data
        if data.get("role") == "true":
            queryset = queryset.filter(
                submissions__in=self.event.submissions.filter(
                    state__in=SubmissionStates.accepted_states
                )
            )
        elif data.get("role") == "false":
            queryset = queryset.exclude(
                submissions__in=self.event.submissions.filter(
                    state__in=SubmissionStates.accepted_states
                )
            )
        if has_arrived := data.get("arrived"):
            queryset = queryset.filter(has_arrived=(has_arrived == "true"))
        return queryset

    class Media:
        js = [forms.Script("orga/js/forms/fulltext-toggle.js", defer="")]
        css = {"all": ["orga/css/forms/search.css"]}


class UserSpeakerFilterForm(forms.Form):
    default_renderer = InlineFormRenderer

    role = forms.ChoiceField(
        choices=(
            ("speaker", phrases.schedule.speakers),
            ("submitter", _("Non-accepted submitters")),
            ("all", phrases.base.all_choices),
        ),
        required=False,
        widget=EnhancedSelect,
    )
    events = SafeModelMultipleChoiceField(
        queryset=Event.objects.none(), required=False, widget=EnhancedSelectMultiple
    )

    def __init__(self, *args, events=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = events
        if len(events) > 1:
            self.fields["events"].queryset = events
        else:
            self.fields.pop("events")

    def filter_queryset(self, qs):
        data = self.cleaned_data
        role = data.get("role") or "speaker"

        if events := data.get("events"):
            qs = qs.filter(profiles__event__in=events)
        if role == "speaker":
            qs = qs.filter(accepted_submission_count__gt=0)
        elif role == "submitter":
            qs = qs.filter(accepted_submission_count=0)
        return qs.order_by("id").distinct()

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}
