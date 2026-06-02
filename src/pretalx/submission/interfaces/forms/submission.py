# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Johan Van de Wauw
# SPDX-FileContributor: Michael Reichert

from django import forms
from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField

from pretalx.cfp.forms import CfPFormMixin, RequestRequire
from pretalx.common.forms.fields import (
    CountableOption,
    ImageField,
    MultiEmailField,
    SubmissionTypeField,
)
from pretalx.common.forms.mixins import ReadOnlyFlag
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    HtmlDateTimeInput,
    MarkdownWidget,
    SearchInput,
    SelectMultipleWithCount,
    TextInputWithAddon,
)
from pretalx.common.text.phrases import phrases
from pretalx.schedule.models import TalkSlot
from pretalx.schedule.validators.slot import (
    validate_slot_time_range,
    validate_slot_within_event,
)
from pretalx.submission.domain.queries.question import filter_submissions_by_question
from pretalx.submission.domain.queries.submission import (
    annotate_submission_count,
    filter_submissions_by_state,
    search_submissions,
    submission_field_counts,
    submission_state_facets,
)
from pretalx.submission.domain.submission import (
    apply_field_changes,
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
)
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import Question, Submission, SubmissionStates, Tag, Track
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

    def _bind_choice_field(self, field, queryset):
        """Wire ``queryset`` to ``field``. If only one value is available
        and the field is required, drop the field and remember the value
        to apply at save() time."""
        self.fields[field].queryset = queryset
        if len(queryset) == 1 and self.fields[field].required:
            self.default_values[field] = queryset.first()
            self.fields.pop(field)

    def _configure_track(self):
        if "track" not in self.fields:
            return
        if self._track_locked():
            self.fields.pop("track")
            return
        self._bind_choice_field(
            "track",
            available_tracks_for_submitter(
                self.event,
                access_code=self._resolved_access_code,
                instance=self.instance,
            ),
        )

    def _configure_submission_types(self):
        queryset = available_submission_types_for_submitter(
            self.event, access_code=self._resolved_access_code, instance=self.instance
        )
        if self._submission_type_locked():
            self.fields["submission_type"].queryset = queryset
            self.fields["submission_type"].disabled = True
            return
        self._bind_choice_field("submission_type", queryset)
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


class SubmissionFilterForm(forms.Form):
    state = forms.MultipleChoiceField(
        required=False,
        choices=[
            (state, name)
            for (state, name) in SubmissionStates.choices
            if state != SubmissionStates.DRAFT
        ],
        widget=SelectMultipleWithCount(
            attrs={"title": _("Proposal states")},
            color_field=SubmissionStates.get_color,
        ),
    )
    submission_type = forms.MultipleChoiceField(
        required=False,
        widget=SelectMultipleWithCount(attrs={"title": _("Session types")}),
    )
    pending_state__isnull = forms.BooleanField(
        required=False, label=_("exclude pending")
    )
    content_locale = forms.MultipleChoiceField(
        required=False,
        widget=SelectMultipleWithCount(attrs={"title": phrases.base.language}),
    )
    track = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Track.objects.none(),
        widget=SelectMultipleWithCount(
            attrs={"title": _("Tracks")}, color_field="color"
        ),
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=SelectMultipleWithCount(attrs={"title": _("Tags")}, color_field="color"),
    )
    question = SafeModelChoiceField(queryset=Question.objects.none(), required=False)
    unanswered = forms.BooleanField(required=False)
    answer = forms.CharField(required=False)
    answer__options = forms.IntegerField(required=False)
    q = forms.CharField(required=False, label=phrases.base.search, widget=SearchInput)
    fulltext = forms.BooleanField(required=False, label=_("Full text search"))

    default_renderer = InlineFormRenderer

    def __init__(
        self,
        event,
        *args,
        limit_tracks=False,
        can_view_speakers=True,
        usable_states=None,
        **kwargs,
    ):
        self.event = event
        self.can_view_speakers = can_view_speakers
        super().__init__(*args, **kwargs)

        submissions = event.submissions
        if usable_states:
            submissions = submissions.filter(state__in=usable_states)

        self._configure_state(usable_states)
        self._configure_submission_type(submissions)
        self._configure_track(limit_tracks)
        self._configure_content_locale(submissions)
        self._configure_tags()
        self.fields["question"].queryset = event.questions.all()

    def _configure_state(self, usable_states):
        """State choices include synthetic ``pending_state__<x>`` entries.

        Both regular and pending-state counts honour ``usable_states`` —
        a "Pending accepted" count covering submissions in unrelated states
        would mislead the reviewer just as much as an unfiltered "accepted"
        count would.
        """
        counts = submission_state_facets(self.event, usable_states=usable_states)
        base = [
            (value, label)
            for value, label in self.fields["state"].choices
            if not usable_states or value in usable_states
        ]
        pending = [
            (f"pending_state__{value}", _("Pending {state}").format(state=label))
            for value, label in base
        ]
        self.fields["state"].choices = [
            (value, CountableOption(str(label).capitalize(), counts.get(value, 0)))
            for value, label in (*base, *pending)
        ]

    def _configure_submission_type(self, submissions):
        sub_types = self.event.submission_types.all()
        if len(sub_types) <= 1:
            self.fields.pop("submission_type", None)
            return
        counts = submission_field_counts(submissions, "submission_type_id")
        self.fields["submission_type"].choices = [
            (t.pk, CountableOption(t.name, counts.get(t.pk, 0))) for t in sub_types
        ]

    def _configure_track(self, limit_tracks):
        if limit_tracks and isinstance(limit_tracks, (list, tuple, set, frozenset)):
            limit_tracks = self.event.tracks.filter(pk__in=limit_tracks)
        tracks = limit_tracks or self.event.tracks.all()
        if len(tracks) <= 1 and self.event.cfp.require_track:
            self.fields.pop("track", None)
            return
        self.fields["track"].queryset = annotate_submission_count(tracks).order_by(
            "-submission_count"
        )

    def _configure_content_locale(self, submissions):
        languages = self.event.named_content_locales
        if len(languages) <= 1:
            self.fields.pop("content_locale", None)
            return
        counts = submission_field_counts(submissions, "content_locale")
        self.fields["content_locale"].choices = [
            (code, CountableOption(name, counts.get(code, 0)))
            for code, name in languages
        ]

    def _configure_tags(self):
        if not self.event.tags.exists():
            self.fields.pop("tags", None)
            return
        self.fields["tags"].queryset = annotate_submission_count(self.event.tags.all())

    def filter_queryset(self, qs):
        for field in ("submission_type", "content_locale", "track", "tags"):
            if value := self.cleaned_data.get(field):
                qs = qs.filter(**{f"{field}__in": value})
        if state_filter := self.cleaned_data.get("state"):
            qs = filter_submissions_by_state(qs, state_filter)
        if self.cleaned_data.get("pending_state__isnull"):
            qs = qs.filter(pending_state__isnull=True)
        qs = search_submissions(
            qs,
            self.cleaned_data.get("q"),
            can_view_speakers=self.can_view_speakers,
            fulltext=bool(self.cleaned_data.get("fulltext")),
        )
        return filter_submissions_by_question(
            qs,
            question=self.cleaned_data.get("question"),
            answer=self.cleaned_data.get("answer"),
            option=self.cleaned_data.get("answer__options"),
            unanswered=self.cleaned_data.get("unanswered"),
        )

    class Media:
        js = [
            forms.Script("orga/js/forms/submissionfilter.js", defer=""),
            forms.Script("orga/js/forms/fulltext-toggle.js", defer=""),
        ]
        css = {"all": ["orga/css/forms/search.css"]}


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
                queryset=event.rooms.all(),
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
        field = self.fields["attendee_signup_required"]
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


class SubmissionSignupFilterForm(forms.Form):
    state = forms.MultipleChoiceField(
        required=False,
        choices=AttendeeSignupStates.choices,
        widget=SelectMultipleWithCount(attrs={"title": _("Signup state")}),
    )

    default_renderer = InlineFormRenderer

    def __init__(self, *args, submission=None, **kwargs):
        self.submission = submission
        super().__init__(*args, **kwargs)
        counts = (
            dict(
                submission.attendee_signups.values("state")
                .annotate(count=Count("state"))
                .values_list("state", "count")
            )
            if submission
            else {}
        )
        self.fields["state"].choices = [
            (value, CountableOption(str(label).capitalize(), counts.get(value, 0)))
            for value, label in AttendeeSignupStates.choices
        ]

    def filter_queryset(self, qs):
        if state_filter := self.cleaned_data.get("state"):
            qs = qs.filter(state__in=state_filter)
        return qs

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}
