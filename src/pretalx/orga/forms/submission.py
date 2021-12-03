import datetime as dt
import json

from django import forms
from django.conf import settings
from django.utils.translation import gettext as _
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField

from pretalx.common.forms.fields import ImageField
from pretalx.common.mixins.forms import ReadOnlyFlag, RequestRequire
from pretalx.submission.models import Submission, SubmissionStates, SubmissionType


class SubmissionForm(ReadOnlyFlag, RequestRequire, forms.ModelForm):
    def __init__(self, event, anonymise=False, **kwargs):
        self.event = event
        initial_slot = {}
        instance = kwargs.get("instance")
        if instance and instance.pk:
            slot = (
                instance.slots.filter(schedule__version__isnull=True)
                .select_related("room")
                .order_by("start")
                .first()
            )
            if slot:
                initial_slot = {
                    "room": slot.room,
                    "start": slot.start.astimezone(self.event.tz).isoformat()
                    if slot.start
                    else "",
                    "end": slot.real_end.astimezone(self.event.tz).isoformat()
                    if slot.real_end
                    else "",
                }
        if anonymise:
            kwargs.pop("initial", None)
            initial = {}
            instance = kwargs.pop("instance", None)
            previous_data = instance.anonymised
            for key in self._meta.fields:
                initial[key] = (
                    previous_data.get(key) or getattr(instance, key, None) or ""
                )
                if hasattr(initial[key], "all"):  # Tags, for the moment
                    initial[key] = initial[key].all()
            kwargs["initial"] = initial
        kwargs["initial"].update(initial_slot)
        super().__init__(**kwargs)
        if "submission_type" in self.fields:
            self.fields["submission_type"].queryset = SubmissionType.objects.filter(
                event=event
            )
        if not self.event.tags.all().exists():
            self.fields.pop("tags", None)
        elif "tags" in self.fields:
            self.fields["tags"].queryset = self.event.tags.all()
            self.fields["tags"].required = False

        self.is_creating = False
        if not self.instance.pk:
            self.is_creating = True
            self.fields["speaker"] = forms.EmailField(
                label=_("Speaker email"),
                help_text=_(
                    "The email address of the speaker holding the session. They will be invited to create an account."
                ),
                required=False,
            )
            self.fields["speaker_name"] = forms.CharField(
                label=_("Speaker name"),
                help_text=_(
                    "The name of the speaker that should be displayed publicly."
                ),
                required=False,
            )
            if not anonymise:
                self.fields["state"] = forms.ChoiceField(
                    label=_("Proposal state"),
                    choices=SubmissionStates.get_choices(),
                    initial=SubmissionStates.SUBMITTED,
                )
        if not self.instance.pk or self.instance.state in (
            SubmissionStates.ACCEPTED,
            SubmissionStates.CONFIRMED,
        ):
            self.fields["room"] = forms.ModelChoiceField(
                required=False,
                queryset=event.rooms.all(),
                label=_("Room"),
                initial=initial_slot.get("room"),
            )
            self.fields["start"] = forms.DateTimeField(
                required=False,
                label=_("Start"),
                widget=forms.DateInput(
                    attrs={
                        "class": "datetimepickerfield",
                        "data-date-start-date": event.date_from.isoformat(),
                        "data-date-end-date": (
                            event.date_to + dt.timedelta(days=1)
                        ).isoformat(),
                        "data-date-before": "#id_end",
                    }
                ),
                initial=initial_slot.get("start"),
            )
            self.fields["end"] = forms.DateTimeField(
                required=False,
                label=_("End"),
                widget=forms.DateInput(
                    attrs={
                        "class": "datetimepickerfield",
                        "data-date-start-date": event.date_from.isoformat(),
                        "data-date-end-date": (
                            event.date_to + dt.timedelta(days=1)
                        ).isoformat(),
                        "data-date-after": "#id_start",
                    }
                ),
                initial=initial_slot.get("end"),
            )
        if "abstract" in self.fields:
            self.fields["abstract"].widget.attrs["rows"] = 2
        if not event.feature_flags["present_multiple_times"]:
            self.fields.pop("slot_count", None)
        if not event.feature_flags["use_tracks"]:
            self.fields.pop("track", None)
        elif "track" in self.fields:
            self.fields["track"].queryset = event.tracks.all()
        if "content_locale" in self.fields:
            if len(event.locales) == 1:
                self.initial["content_locale"] = event.locales[0]
                self.fields["content_locale"].widget = forms.HiddenInput()
            else:
                locale_names = dict(settings.LANGUAGES)
                self.fields["content_locale"].choices = [
                    (a, locale_names[a]) for a in event.locales
                ]

    def save(self, *args, **kwargs):
        if "content_locale" not in self.fields:
            self.instance.content_locale = self.event.locale
        instance = super().save(*args, **kwargs)
        if self.is_creating:
            instance._set_state(self.cleaned_data["state"], force=True)
        else:
            if instance.pk and "duration" in self.changed_data:
                instance.update_duration()
            if instance.pk and "track" in self.changed_data:
                instance.update_review_scores()
            if "slot_count" in self.changed_data and "slot_count" in self.initial:
                instance.update_talk_slots()
        if (
            instance.state
            in (
                SubmissionStates.ACCEPTED,
                SubmissionStates.CONFIRMED,
            )
            and self.cleaned_data.get("room")
            and self.cleaned_data.get("start")
            and any(field in self.changed_data for field in ("room", "start", "end"))
        ):
            slot = (
                instance.slots.filter(schedule=instance.event.wip_schedule)
                .order_by("start")
                .first()
            )
            slot.room = self.cleaned_data.get("room")
            slot.start = self.cleaned_data.get("start")
            slot.end = self.cleaned_data.get("end")
            slot.save()
        return instance

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
        ]
        widgets = {
            "tags": forms.SelectMultiple(attrs={"class": "select2"}),
            "track": forms.Select(attrs={"class": "select2"}),
            "submission_type": forms.Select(attrs={"class": "select2"}),
        }
        field_classes = {
            "submission_type": SafeModelChoiceField,
            "tags": SafeModelMultipleChoiceField,
            "track": SafeModelChoiceField,
            "image": ImageField,
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


class AnonymiseForm(SubmissionForm):
    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        if not instance or not instance.pk:
            raise Exception("Cannot anonymise unsaved submission.")
        kwargs["event"] = instance.event
        kwargs["anonymise"] = True
        super().__init__(*args, **kwargs)
        self._instance = instance
        to_be_removed = []
        for key, field in self.fields.items():
            try:
                field.plaintext = getattr(self._instance, key)
                field.required = False
            except AttributeError:
                to_be_removed.append(key)
        for key in to_be_removed:
            self.fields.pop(key)

    def save(self):
        anonymised_data = {"_anonymised": True}
        for key, value in self.cleaned_data.items():
            if value != getattr(self._instance, key, ""):
                anonymised_data[key] = value
        self._instance.anonymised_data = json.dumps(anonymised_data)
        self._instance.save(update_fields=["anonymised_data"])

    class Meta:
        model = Submission
        fields = [
            "title",
            "abstract",
            "description",
            "notes",
        ]
        request_require = fields
