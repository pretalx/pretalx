# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Johan Van de Wauw
# SPDX-FileContributor: Michael Reichert

from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField

from pretalx.cfp.forms import CfPFormMixin, RequestRequire
from pretalx.common.forms.fields import ImageField, MultiEmailField, SubmissionTypeField
from pretalx.common.forms.mixins import ReadOnlyFlag
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    HtmlDateTimeInput,
    MarkdownWidget,
    TextInputWithAddon,
)
from pretalx.common.text.phrases import phrases
from pretalx.schedule.models import TalkSlot
from pretalx.schedule.validators.slot import (
    validate_slot_time_range,
    validate_slot_within_event,
)
from pretalx.submission.domain.submission import (
    apply_field_changes,
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
)
from pretalx.submission.models import Submission, SubmissionStates, Tag
from pretalx.submission.validators.speaker import validate_speakers_within_limit


class SubmissionInfoForm(CfPFormMixin, ReadOnlyFlag, RequestRequire, forms.ModelForm):
    """The proposal form shown to speakers.

    Used by the speaker-side edit view. Compared to the orga-side
    ``SubmissionForm``, this filters submission types and tracks to what
    the speaker is allowed to choose from (access codes, deadlines,
    current state), locks fields once a submission has moved past
    SUBMITTED or the CfP has closed, and exposes only public tags
    (merging private tags back in on save).

    See ``InfoForm`` for the CfP-flow variant that adds the additional-
    speaker invitation field.
    """

    image = ImageField(
        required=False, label=_("Session image"), help_text=phrases.base.image_help
    )
    content_locale = forms.ChoiceField(label=phrases.base.language)
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        label=_("Tags"),
        required=False,
        widget=EnhancedSelectMultiple(color_field="color"),
    )

    def __init__(self, event, **kwargs):
        self.event = event
        self.access_code = kwargs.pop("access_code", None)
        self.default_values = {}
        instance = kwargs.get("instance")
        initial = kwargs.pop("initial", {}) or {}
        self._prefill_initial(initial, instance=instance)

        super().__init__(initial=initial, **kwargs)

        self._configure_track()
        self._configure_submission_types()
        self._configure_locales()
        self._configure_slot_count()
        self._configure_tags()

    def _prefill_initial(self, initial, *, instance):
        """Fill in defaults for fields whose value is otherwise ambiguous
        for a fresh proposal: the submission type, track, and content
        locale. Mutates ``initial`` in place."""
        if not instance or not instance.submission_type:
            access_code_type = (
                self.access_code.submission_types.first() if self.access_code else None
            )
            initial["submission_type"] = (
                access_code_type
                or initial.get("submission_type")
                or self.event.cfp.default_type
            )
        if not instance and self.access_code:
            initial["track"] = self.access_code.tracks.first()
        if not instance or not instance.content_locale:
            initial["content_locale"] = self.event.locale

    @property
    def _resolved_access_code(self):
        return self.access_code or self.instance.access_code

    def _track_locked(self):
        return not self.event.has_active_tracks or (
            not self.instance._state.adding
            and self.instance.state != SubmissionStates.SUBMITTED
        )

    def _submission_type_locked(self):
        return bool(
            not self.instance._state.adding
            and (
                self.instance.state != SubmissionStates.SUBMITTED
                or not self.event.cfp.is_open
            )
        )

    def _bind_choice_field(self, field, queryset, restricted_by_access_code):
        self.fields[field].queryset = queryset
        if len(queryset) != 1 or not self.fields[field].required:
            return
        value = queryset.first()
        self.default_values[field] = value
        if not restricted_by_access_code:
            self.fields.pop(field)
            return
        self.initial[field] = value
        form_field = self.fields[field]
        form_field.disabled = True

    def _configure_track(self):
        if "track" not in self.fields:
            return
        if self._track_locked():
            self.fields.pop("track")
            return
        tracks, restricted_by_access_code = available_tracks_for_submitter(
            self.event, access_code=self._resolved_access_code, instance=self.instance
        )
        self._bind_choice_field("track", tracks, restricted_by_access_code)

    def _configure_submission_types(self):
        types, restricted_by_access_code = available_submission_types_for_submitter(
            self.event, access_code=self._resolved_access_code, instance=self.instance
        )
        if self._submission_type_locked():
            self.fields["submission_type"].queryset = types
            self.fields["submission_type"].disabled = True
            return
        self._bind_choice_field("submission_type", types, restricted_by_access_code)
        if (
            "submission_type" in self.fields
            and "duration" in self.fields
            and not self.fields["duration"].required
        ):
            self.fields["duration"].help_text += " " + str(phrases.base.duration_help)

    def _configure_locales(self):
        locales = self.event.content_locales
        if "content_locale" not in self.fields or len(locales) == 1:
            self.default_values["content_locale"] = locales[0]
            self.fields.pop("content_locale", None)
        else:
            self.fields["content_locale"].choices = self.event.named_content_locales

    def _configure_slot_count(self):
        if not self.event.get_feature_flag("present_multiple_times"):
            self.fields.pop("slot_count", None)
        elif (
            "slot_count" in self.fields
            and not self.instance._state.adding
            and self.instance.state in SubmissionStates.accepted_states
        ):
            self.fields["slot_count"].disabled = True
            self.fields["slot_count"].help_text += " " + str(
                _(
                    "Please contact the organisers if you want to change how often you’re presenting this proposal."
                )
            )

    def _configure_tags(self):
        if "tags" not in self.fields:
            return
        public_tags = self.event.tags.filter(is_public=True)
        if not public_tags.exists():
            self.fields.pop("tags")
            return
        self.fields["tags"].queryset = public_tags
        if not self.instance._state.adding:
            self.initial["tags"] = self.instance.tags.filter(is_public=True)

    def clean_tags(self):
        tags = set(self.cleaned_data.get("tags") or ())
        if not self.instance._state.adding:
            tags |= set(self.instance.tags.filter(is_public=False))
        return tags

    def save(self, commit=True, **kwargs):
        for key, value in self.default_values.items():
            setattr(self.instance, key, value)
        result = super().save(commit=commit, **kwargs)
        # Image processing requires a saved row; with commit=False the
        # caller is responsible for it after persisting the instance.
        if commit and "image" in self.cleaned_data:
            self.instance.process_image("image")
        return result

    class Media:
        css = {"all": ["common/css/forms/resource.css"]}

    class Meta:
        model = Submission
        fields = [
            "title",
            "submission_type",
            "track",
            "content_locale",
            "abstract",
            "description",
            "notes",
            "slot_count",
            "do_not_record",
            "image",
            "duration",
            "tags",
        ]
        request_require = [
            "title",
            "abstract",
            "description",
            "notes",
            "image",
            "do_not_record",
            "track",
            "duration",
            "content_locale",
            "tags",
        ]
        public_fields = ["title", "abstract", "description", "image"]
        widgets = {
            "track": EnhancedSelect(
                description_field="description", color_field="color"
            ),
            "abstract": MarkdownWidget(attrs={"rows": 2}),
        }
        field_classes = {
            "submission_type": SubmissionTypeField,
            "track": SafeModelChoiceField,
        }


class InfoForm(SubmissionInfoForm):
    """CfP-flow variant of ``SubmissionInfoForm``.

    Adds a free-form list of email addresses for additional speakers,
    capped by the per-event speaker limit. Used by the CfP submission
    flow (``InfoStep``) and its orga-side read-only preview.
    """

    additional_speaker = MultiEmailField(
        label=_("Additional speakers"),
        help_text=_(
            "If you have co-speakers, please add their email addresses here, "
            "and we will invite them to create an account."
        ),
        required=False,
    )

    def _prefill_initial(self, initial, *, instance):
        super()._prefill_initial(initial, instance=instance)
        # Drafts hold deferred invitations on ``draft_additional_speakers`` so
        # the field is repopulated when the speaker resumes the wizard.
        if (
            instance
            and not instance._state.adding
            and instance.draft_additional_speakers
        ):
            initial.setdefault(
                "additional_speaker", ", ".join(instance.draft_additional_speakers)
            )

    def clean_additional_speaker(self):
        emails = self.cleaned_data.get("additional_speaker", [])
        if not emails:
            return emails
        if not self.instance._state.adding:
            # An email already pending must not be counted again as a new
            # invitation when the user re-submits a draft whose form still
            # carries the address.
            already_invited = {
                e.lower()
                for e in self.instance.invitations.values_list("email", flat=True)
            }
            new_count = sum(1 for e in emails if e.lower() not in already_invited)
            current = self.instance.speakers.count()
            pending = self.instance.invitations.count()
        else:
            # An unsaved proposal has the submitter as its first speaker.
            new_count = len(emails)
            current = 1
            pending = 0
        if new_count:
            validate_speakers_within_limit(
                self.event, current=current, pending=pending, additional=new_count
            )
        return emails

    class Meta(SubmissionInfoForm.Meta):
        request_require = [
            *SubmissionInfoForm.Meta.request_require,
            "additional_speaker",
        ]


class SubmissionOrgaForm(ReadOnlyFlag, RequestRequire, forms.ModelForm):
    content_locale = forms.ChoiceField(label=phrases.base.language)

    def __init__(self, event, anonymise=False, **kwargs):
        self.event = event
        initial_slot = {}
        instance = kwargs.get("instance")
        if instance and not instance._state.adding:
            slot = (
                instance.slots.filter(schedule__version__isnull=True)
                .select_related("room")
                .filter(start__isnull=False)
                .order_by("start")
                .first()
            )
            if slot:
                initial_slot = {
                    "room": slot.room,
                    "start": slot.local_start,
                    "end": slot.local_end,
                }
        if anonymise:
            kwargs.pop("initial", None)
            initial = {}
            instance = kwargs.pop("instance", None)
            previous_data = instance.anonymised or {}
            for key in self._meta.fields:
                initial[key] = (
                    previous_data.get(key) or getattr(instance, key, None) or ""
                )
                if hasattr(initial[key], "all"):  # Tags, for the moment
                    initial[key] = initial[key].all()
            kwargs["initial"] = initial
        kwargs["initial"] = kwargs.get("initial") or {}
        kwargs["initial"].update(initial_slot)
        super().__init__(**kwargs)
        if "submission_type" in self.fields:
            self.fields["submission_type"].queryset = self.event.submission_types.all()
        if not self.event.tags.exists():
            self.fields.pop("tags", None)
        elif "tags" in self.fields:
            self.fields["tags"].queryset = self.event.tags.all()
            self.fields["tags"].required = False

        if self.instance._state.adding and not anonymise:
            state_field = self.fields["state"]
            state_field.choices = [
                choice
                for choice in state_field.choices
                if choice[0] != SubmissionStates.DRAFT
            ]
            state_field.initial = SubmissionStates.SUBMITTED
        else:
            self.fields.pop("state", None)
        if (
            self.instance._state.adding
            or self.instance.state in SubmissionStates.accepted_states
        ):
            self.fields["room"] = forms.ModelChoiceField(
                required=False,
                queryset=event.rooms.visible(),
                label=TalkSlot._meta.get_field("room").verbose_name,
                initial=initial_slot.get("room"),
                widget=EnhancedSelect,
            )
            self.fields["start"] = forms.DateTimeField(
                required=False,
                label=TalkSlot._meta.get_field("start").verbose_name,
                widget=HtmlDateTimeInput,
                initial=initial_slot.get("start"),
            )
            self.fields["end"] = forms.DateTimeField(
                required=False,
                label=TalkSlot._meta.get_field("end").verbose_name,
                widget=HtmlDateTimeInput,
                initial=initial_slot.get("end"),
            )
        if "abstract" in self.fields:
            self.fields["abstract"].widget.attrs["rows"] = 2
        if not event.get_feature_flag("present_multiple_times"):
            self.fields.pop("slot_count", None)
        if not event.has_active_tracks:
            self.fields.pop("track", None)
        elif "track" in self.fields:
            self.fields["track"].queryset = event.tracks.all()
        if "content_locale" in self.fields:
            if len(event.content_locales) == 1:
                self.fields.pop("content_locale")
            else:
                self.fields["content_locale"].choices = self.event.named_content_locales
        # If duration is not required, point out that the default is the session type's duration,
        # but only if there is more than one session type, because otherwise users will be
        # confused what that is.
        if (
            "duration" in self.fields
            and not self.fields["duration"].required
            and "submission_type" in self.fields
            and len(self.fields["submission_type"].queryset) > 1
        ):
            self.fields["duration"].help_text += " " + str(phrases.base.duration_help)
        self._configure_attendee_signup_required()

    def _configure_attendee_signup_required(self):
        if not self.event.get_feature_flag("attendee_signup"):
            self.fields.pop("attendee_signup_required", None)
            return
        field = self.fields.get("attendee_signup_required")
        if not field:
            return
        required_label = _("Requires signup")
        not_required_label = _("No signup")
        track = self.instance.track if self.instance.track_id else None
        submission_type = (
            self.instance.submission_type if self.instance.submission_type_id else None
        )
        inherited_default = bool(track and track.attendee_signup_required) or bool(
            submission_type and submission_type.attendee_signup_required
        )
        empty_label = _("Default (currently: {value})").format(
            value=required_label if inherited_default else not_required_label
        )
        field.choices = [
            ("unknown", empty_label),
            ("true", required_label),
            ("false", not_required_label),
        ]
        if (
            not self.instance._state.adding
            and self.instance.attendee_signup_required is True
        ):
            self.initial["attendee_signup_required"] = "true"
        elif (
            not self.instance._state.adding
            and self.instance.attendee_signup_required is False
        ):
            self.initial["attendee_signup_required"] = "false"
        else:
            self.initial["attendee_signup_required"] = "unknown"

    def clean_attendee_signup_required(self):
        value = self.cleaned_data.get("attendee_signup_required")
        if value == "true":
            return True
        if value == "false":
            return False
        return None

    def clean_start(self):
        value = self.cleaned_data.get("start")
        validate_slot_within_event(value, event=self.event)
        return value

    def clean_end(self):
        value = self.cleaned_data.get("end")
        validate_slot_within_event(value, event=self.event)
        return value

    def clean(self):
        data = super().clean()
        start = data.get("start")
        end = data.get("end")
        room = data.get("room")
        try:
            validate_slot_time_range(start=start, end=end)
        except forms.ValidationError as exc:
            self.add_error("end", exc)
        if room and not start:
            self.add_error(
                "room",
                forms.ValidationError(
                    _(
                        "You cannot assign a room without setting the start time as well."
                    )
                ),
            )
        if start and not room:
            self.add_error(
                "start",
                forms.ValidationError(
                    _("You cannot set a start time without assigning the room as well.")
                ),
            )
        return data

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        apply_field_changes(instance, self.changed_data)
        return instance

    def scheduling_kwargs(self):
        """Return ``room``/``start``/``end`` for ``set_wip_slot``, or ``None``.

        Returns ``None`` unless all three scheduling fields are present on the
        form and carry values; otherwise the cleaned values for the caller.
        """
        scheduling_fields = ("room", "start", "end")
        if not all(field in self.fields for field in scheduling_fields):
            return None
        kwargs = {field: self.cleaned_data.get(field) for field in scheduling_fields}
        if not all(kwargs.values()):
            return None
        return kwargs

    class Media:
        js = [forms.Script("orga/js/forms/submission.js", defer="")]
        css = {"all": ["common/css/forms/resource.css"]}

    class Meta:
        model = Submission
        fields = [
            "title",
            "submission_type",
            "track",
            "tags",
            "abstract",
            "description",
            "notes",
            "internal_notes",
            "content_locale",
            "do_not_record",
            "duration",
            "slot_count",
            "image",
            "is_featured",
            "state",
            "attendee_signup_required",
        ]
        widgets = {
            "tags": EnhancedSelectMultiple(color_field="color"),
            "track": EnhancedSelect(color_field="color"),
            "submission_type": EnhancedSelect,
            "duration": TextInputWithAddon(addon_after=_("minutes")),
            "state": EnhancedSelect(color_field=SubmissionStates.get_color),
        }
        field_classes = {
            "submission_type": SafeModelChoiceField,
            "tags": SafeModelMultipleChoiceField,
            "track": SafeModelChoiceField,
            "image": ImageField,
            "attendee_signup_required": forms.ChoiceField,
        }
        request_require = {
            "title",
            "abstract",
            "description",
            "notes",
            "image",
            "do_not_record",
            "content_locale",
        }


class AnonymiseForm(SubmissionOrgaForm):
    default_renderer = InlineFormRenderer

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        if not instance or instance._state.adding:
            raise ValueError("Cannot anonymise unsaved submission.")
        kwargs["event"] = instance.event
        kwargs["anonymise"] = True
        super().__init__(*args, **kwargs)
        self._instance = instance
        to_be_removed = ["content_locale"]
        for key, field in self.fields.items():
            try:
                field.plaintext = getattr(self._instance, key)
                field.required = False
            except AttributeError:
                to_be_removed.append(key)
        for key in to_be_removed:
            self.fields.pop(key, None)

    def save(self):
        self._instance.anonymised = {
            "_anonymised": True,
            **{
                key: value
                for key, value in self.cleaned_data.items()
                if value != getattr(self._instance, key, "")
            },
        }
        self._instance.save(update_fields=["anonymised"])

    class Media:
        js = [forms.Script("orga/js/forms/anonymise.js", defer="")]
        css = {"all": ["orga/css/forms/anonymise.css"]}

    class Meta:
        model = Submission
        fields = ["title", "abstract", "description", "notes"]
        request_require = fields


class SubmissionSignupForm(ReadOnlyFlag, forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["attendee_signup_capacity"]
