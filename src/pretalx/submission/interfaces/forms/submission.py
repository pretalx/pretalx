# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Johan Van de Wauw
# SPDX-FileContributor: Michael Reichert

from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.cfp.forms.cfp import CfPFormMixin
from pretalx.common.forms.fields import (
    CountableOption,
    ImageField,
    MultiEmailField,
    SubmissionTypeField,
)
from pretalx.common.forms.mixins import ReadOnlyFlag, RequestRequire
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    MarkdownWidget,
    SearchInput,
    SelectMultipleWithCount,
)
from pretalx.common.text.phrases import phrases
from pretalx.submission.domain.queries.question import filter_submissions_by_question
from pretalx.submission.domain.queries.submission import (
    filter_submissions_by_state,
    search_submissions,
    submission_field_counts,
    submission_state_facets,
    tags_with_submission_counts,
    tracks_with_submission_counts,
)
from pretalx.submission.domain.submission import (
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
)
from pretalx.submission.interfaces.validators.speaker import (
    validate_speakers_within_limit,
)
from pretalx.submission.models import Question, Submission, SubmissionStates, Tag, Track


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

        self._set_track()
        self._set_submission_types()
        self._set_locales()
        self._set_slot_count()
        self._set_tags()

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
        return not self.event.get_feature_flag("use_tracks") or (
            self.instance.pk and self.instance.state != SubmissionStates.SUBMITTED
        )

    def _submission_type_locked(self):
        return bool(
            self.instance.pk
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

    def _set_track(self):
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

    def _set_submission_types(self):
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

    def _set_locales(self):
        locales = self.event.content_locales
        if "content_locale" not in self.fields or len(locales) == 1:
            self.default_values["content_locale"] = locales[0]
            self.fields.pop("content_locale", None)
        else:
            self.fields["content_locale"].choices = self.event.named_content_locales

    def _set_slot_count(self):
        if not self.event.get_feature_flag("present_multiple_times"):
            self.fields.pop("slot_count", None)
        elif (
            "slot_count" in self.fields
            and self.instance.pk
            and self.instance.state in SubmissionStates.accepted_states
        ):
            self.fields["slot_count"].disabled = True
            self.fields["slot_count"].help_text += " " + str(
                _(
                    "Please contact the organisers if you want to change how often you’re presenting this proposal."
                )
            )

    def _set_tags(self):
        if "tags" not in self.fields:
            return
        public_tags = self.event.tags.filter(is_public=True)
        if not public_tags.exists():
            self.fields.pop("tags")
            return
        self.fields["tags"].queryset = public_tags
        if self.instance.pk:
            self.initial["tags"] = self.instance.tags.filter(is_public=True)

    def clean_tags(self):
        tags = set(self.cleaned_data.get("tags") or ())
        if self.instance.pk:
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
        if instance and instance.pk and instance.draft_additional_speakers:
            initial.setdefault(
                "additional_speaker", ", ".join(instance.draft_additional_speakers)
            )

    def clean_additional_speaker(self):
        emails = self.cleaned_data.get("additional_speaker", [])
        if not emails:
            return emails
        if self.instance.pk:
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
        if limit_tracks and isinstance(limit_tracks, (list, tuple, set)):
            limit_tracks = self.event.tracks.filter(pk__in=[t.pk for t in limit_tracks])
        tracks = limit_tracks or self.event.tracks.all()
        if len(tracks) <= 1 and self.event.cfp.require_track:
            self.fields.pop("track", None)
            return
        self.fields["track"].queryset = tracks_with_submission_counts(
            self.event, queryset=tracks
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
        if not self.event.tags.all().exists():
            self.fields.pop("tags", None)
            return
        self.fields["tags"].queryset = tags_with_submission_counts(self.event)

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
