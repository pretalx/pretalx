# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from pretalx.cfp.forms import CfPFormMixin, RequestRequire, cfp_field_label
from pretalx.common.forms.fields import AvailabilitiesField, ProfilePictureField
from pretalx.common.forms.mixins import ReadOnlyFlag
from pretalx.mail.domain.placeholders import placeholders_for_template
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.mail.validators import validate_invitation_text
from pretalx.person.domain.profile import (
    MERGE_PROFILE_FIELDS,
    apply_speaker_profile_changes,
)
from pretalx.person.domain.queries.profile import other_speaker_profiles
from pretalx.person.interfaces.forms.widgets import BiographyWidget
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.domain.queries.question import active_questions
from pretalx.submission.models import QuestionTarget


class SpeakerProfileForm(CfPFormMixin, ReadOnlyFlag, RequestRequire, forms.ModelForm):
    availabilities = AvailabilitiesField()
    avatar = ProfilePictureField()

    def __init__(
        self,
        *args,
        event,
        name=None,
        with_email=True,
        essential_only=False,
        is_orga=False,
        **kwargs,
    ):
        self.event = event
        self.essential_only = essential_only
        self.is_orga = is_orga
        instance = kwargs.get("instance")
        self.user = instance.user if instance else None
        self._show_email = with_email and instance is not None and not essential_only
        self._show_locale = (
            is_orga
            and not essential_only
            and instance is not None
            and len(event.named_locales) > 1
        )

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
            email_field = self.fields["email"]
            account_email = self.user.email if self.user else None
            if account_email:
                email_field.widget.attrs.setdefault("placeholder", account_email)
                if not email_field.help_text:
                    email_field.help_text = _(
                        "Leave empty to use the account email address ({email})."
                    ).format(email=account_email)
        else:
            self.fields.pop("email", None)

        if self._show_locale:
            locale_field = self.fields["locale"]
            locale_names = dict(self.event.named_locales)
            fallback = self.user.locale if self.user else None
            if fallback not in self.event.locales:
                fallback = self.event.locale
            locale_field.choices = [
                (
                    "",
                    _("Automatic ({locale})").format(
                        locale=locale_names.get(fallback, fallback)
                    ),
                ),
                *self.event.named_locales,
            ]
        else:
            self.fields.pop("locale", None)

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
        else:
            for field_name, field in self.fields.items():
                if label := cfp_field_label(self.event, field_name):
                    field.label = label

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

    def clean_email(self):
        return self.cleaned_data.get("email") or None

    def clean_locale(self):
        return self.cleaned_data.get("locale") or None

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
        apply_speaker_profile_changes(self.instance, self.changed_data)
        return self.instance

    class Meta:
        model = SpeakerProfile
        fields = ("email", "locale", "biography", "internal_notes")
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


class SpeakerInviteForm(forms.Form):
    subject = forms.CharField(label=_("Subject"))
    text = forms.CharField(label=_("Text"), widget=forms.Textarea)

    def __init__(self, *args, profile, **kwargs):
        self.profile = profile
        self.template = mail_template_by_role(
            profile.event, MailTemplateRoles.STANDALONE_SPEAKER_INVITE
        )
        initial = kwargs.setdefault("initial", {})
        with override(profile.effective_locale):
            initial.setdefault("subject", str(self.template.subject))
            initial.setdefault("text", str(self.template.text))
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        placeholders = placeholders_for_template(self.template)
        for field in ("subject", "text"):
            if value := data.get(field):
                try:
                    validate_invitation_text(
                        value, placeholders, require_invitation_link=field == "text"
                    )
                except forms.ValidationError as exc:
                    self.add_error(field, exc)
        return data


class SpeakerMergeForm(forms.Form):
    """Left/right chooser for the claim-merge page."""

    def __init__(self, *args, merged, survivor, **kwargs):
        self.merged = merged
        self.survivor = survivor
        self.event = merged.event
        super().__init__(*args, **kwargs)
        self.items = []
        locale_names = dict(self.event.named_locales)
        for field in MERGE_PROFILE_FIELDS:
            merged_value = getattr(merged, field) or ""
            survivor_value = getattr(survivor, field) or ""
            if field == "locale":
                merged_value = locale_names.get(merged_value, merged_value)
                survivor_value = locale_names.get(survivor_value, survivor_value)
            self._add_item(
                field,
                label=cfp_field_label(
                    self.event,
                    field,
                    default=SpeakerProfile._meta.get_field(field).verbose_name,
                ),
                kind="markdown" if field == "biography" else "text",
                merged_value=merged_value,
                survivor_value=survivor_value,
            )
        if merged.profile_picture_id or survivor.profile_picture_id:
            self._add_item(
                "picture",
                label=_("Profile picture"),
                kind="picture",
                merged_value=merged.profile_picture,
                survivor_value=survivor.profile_picture,
            )
        merged_availabilities = list(merged.availabilities.all())
        survivor_availabilities = list(survivor.availabilities.all())
        if merged_availabilities or survivor_availabilities:
            self._add_item(
                "availability",
                label=_("Availability"),
                kind="availability",
                merged_value=merged_availabilities,
                survivor_value=survivor_availabilities,
            )
        questions = active_questions(self.event, target=QuestionTarget.SPEAKER)
        merged_answers = {
            answer.question_id: answer
            for answer in merged.answers.filter(question__in=questions)
        }
        survivor_answers = {
            answer.question_id: answer
            for answer in survivor.answers.filter(question__in=questions)
        }
        for question in questions:
            merged_answer = merged_answers.get(question.pk)
            survivor_answer = survivor_answers.get(question.pk)
            if not merged_answer and not survivor_answer:
                continue
            self._add_item(
                f"question_{question.pk}",
                label=question.question,
                kind="text",
                merged_value=merged_answer.answer_string if merged_answer else "",
                survivor_value=survivor_answer.answer_string if survivor_answer else "",
            )

    def _add_item(self, name, *, label, kind, merged_value, survivor_value):
        if not merged_value and not survivor_value:
            return
        self.fields[name] = forms.ChoiceField(
            choices=(
                ("merged", _("Use the organisers’ version")),
                ("survivor", _("Keep your own version")),
            ),
            widget=forms.RadioSelect,
            required=True,
            initial="survivor" if survivor_value else "merged",
            label=label,
        )
        self.items.append(
            {
                "field": self[name],
                "label": label,
                "kind": kind,
                "merged": merged_value,
                "survivor": survivor_value,
            }
        )


__all__ = [
    "OrgaProfileForm",
    "SpeakerAvailabilityForm",
    "SpeakerMergeForm",
    "SpeakerProfileForm",
]
