# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json
from functools import partial

from django import forms
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField
from i18nfield.strings import LazyI18nString

from pretalx.cfp.forms import CfPFormMixin, RequestRequire
from pretalx.common.forms.fields import ExtensionFileField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.validators import (
    MaxDateTimeValidator,
    MaxDateValidator,
    MinDateTimeValidator,
    MinDateValidator,
)
from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    HtmlDateInput,
    HtmlDateTimeInput,
    IconSelect,
)
from pretalx.common.templatetags.rich_text import rich_text
from pretalx.common.text.phrases import phrases
from pretalx.submission.domain.queries.question import (
    active_questions,
    question_answer_summary,
)
from pretalx.submission.domain.question import apply_uploaded_options, save_answer
from pretalx.submission.enums import QuestionRequired, SubmissionStates
from pretalx.submission.models import (
    AnswerOption,
    Question,
    QuestionTarget,
    QuestionVariant,
    SubmissionType,
    Track,
)

FILE_EXTENSIONS = {
    ".png": ["image/png", ".png"],
    ".jpg": ["image/jpeg", ".jpg"],
    ".gif": ["image/gif", ".gif"],
    ".jpeg": ["image/jpeg", ".jpeg"],
    ".bmp": ["image/bmp", ".bmp"],
    ".tif": ["image/tiff", ".tif"],
    ".tiff": ["image/tiff", ".tiff"],
    ".pdf": [
        "application/pdf",
        "application/x-pdf",
        "application/acrobat",
        "applications/vnd.pdf",
        ".pdf",
    ],
    ".txt": ["text/plain"],
    ".docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        ".docx",
    ],
    "doc": [".doc"],
    "rtf": ["application/rtf"],
    ".pptx": [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint",
        ".pptx",
    ],
    ".ppt": [".ppt"],
    ".xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        ".xlsx",
    ],
    ".xls": [".xls"],
}


def _build_boolean(*, question, initial, help_text, **kwargs):
    widget = forms.CheckboxInput(
        attrs={"required": "required"} if question.required else {}
    )
    return forms.BooleanField(
        widget=widget,
        help_text=help_text,
        initial=((initial == "True") if initial else bool(question.default_answer)),
    )


def _build_number(*, question, initial, help_text, **kwargs):
    return forms.DecimalField(
        help_text=help_text,
        initial=initial,
        min_value=question.min_number,
        max_value=question.max_number,
    )


def _build_url(*, initial, help_text, **kwargs):
    return forms.URLField(help_text=help_text, initial=initial)


def _build_file(*, initial, help_text, **kwargs):
    return ExtensionFileField(
        help_text=help_text, initial=initial, extensions=FILE_EXTENSIONS
    )


def _build_choices(*, question, initial_object, help_text, **kwargs):
    choices = question.options.all()
    return forms.ModelChoiceField(
        queryset=choices,
        widget=(forms.RadioSelect if len(choices) < 4 else EnhancedSelect),
        help_text=help_text,
        initial=(
            initial_object.options.first()
            if initial_object
            else question.default_answer
        ),
        empty_label=None,
    )


def _build_multiple(*, question, initial_object, help_text, **kwargs):
    choices = question.options.all()
    return forms.ModelMultipleChoiceField(
        queryset=choices,
        widget=(
            forms.CheckboxSelectMultiple if len(choices) < 8 else EnhancedSelectMultiple
        ),
        help_text=help_text,
        initial=(
            initial_object.options.all() if initial_object else question.default_answer
        ),
    )


def _text_field(*, question, initial, help_text, multiline, **kwargs):
    count_in = question.event.cfp.settings["count_length_in"]
    field = forms.CharField(
        widget=forms.Textarea() if multiline else forms.TextInput(),
        help_text=RequestRequire.get_help_text(
            help_text, question.min_length, question.max_length, count_in
        ),
        initial=initial,
    )
    if count_in == "chars":
        if question.min_length:
            field.widget.attrs["data-minlength"] = question.min_length
        if question.max_length:
            field.widget.attrs["data-maxlength"] = question.max_length
    field.validators.append(
        partial(
            RequestRequire.validate_field_length,
            min_length=question.min_length,
            max_length=question.max_length,
            count_in=count_in,
        )
    )
    return field


def _build_date(*, question, initial, help_text, **kwargs):
    attrs = {}
    if question.min_date:
        attrs["data-date-start-date"] = question.min_date.isoformat()
    if question.max_date:
        attrs["data-date-end-date"] = question.max_date.isoformat()
    field = forms.DateField(
        widget=HtmlDateInput(attrs=attrs),
        help_text=help_text,
        initial=dt.datetime.fromisoformat(initial).date() if initial else None,
    )
    _attach_validator(field, question.min_date, MinDateValidator)
    _attach_validator(field, question.max_date, MaxDateValidator)
    return field


def _build_datetime(*, question, initial, help_text, **kwargs):
    attrs = {}
    if question.min_datetime:
        attrs["min"] = question.min_datetime.isoformat()
    if question.max_datetime:
        attrs["max"] = question.max_datetime.isoformat()
    field = forms.DateTimeField(
        widget=HtmlDateTimeInput(attrs=attrs),
        help_text=help_text,
        initial=(
            dt.datetime.fromisoformat(initial).astimezone(question.event.tz)
            if initial
            else None
        ),
    )
    _attach_validator(field, question.min_datetime, MinDateTimeValidator)
    _attach_validator(field, question.max_datetime, MaxDateTimeValidator)
    return field


def _attach_validator(field, value, validator):
    if value:
        field.validators.append(validator(value))


_BUILDERS = {
    QuestionVariant.BOOLEAN: _build_boolean,
    QuestionVariant.NUMBER: _build_number,
    QuestionVariant.STRING: partial(_text_field, multiline=False),
    QuestionVariant.TEXT: partial(_text_field, multiline=True),
    QuestionVariant.URL: _build_url,
    QuestionVariant.FILE: _build_file,
    QuestionVariant.CHOICES: _build_choices,
    QuestionVariant.MULTIPLE: _build_multiple,
    QuestionVariant.DATE: _build_date,
    QuestionVariant.DATETIME: _build_datetime,
}

_TARGET_ATTR = {
    QuestionTarget.SUBMISSION: "submission",
    QuestionTarget.SPEAKER: "speaker",
    QuestionTarget.REVIEWER: "review",
}


def build_question_field(*, question, target_object=None, read_only=False):
    """Build a Django form field for a Question, by variant.

    ``target_object`` is the parent (Submission, SpeakerProfile, or Review)
    the answer belongs to; if it has an existing answer for ``question``,
    the field is pre-populated from it. Otherwise ``question.default_answer``
    is used.
    """
    initial, initial_object = _initial_for_question(question, target_object)
    help_text = rich_text(question.help_text)[len("<p>") : -len("</p>")]
    field = _BUILDERS[question.variant](
        question=question,
        initial=initial,
        initial_object=initial_object,
        help_text=help_text,
    )
    field.disabled = read_only or question.read_only
    field.label = question.question
    field.required = question.required
    field.original_help_text = question.help_text
    field.widget.attrs.setdefault("placeholder", "")  # XSS
    field.question = question
    field.answer = initial_object
    return field


def _initial_for_question(question, target_object):
    if target_object:
        for answer in target_object.answers.all():
            # Manual lookup to avoid re-querying the DB; looping once for every
            # question is still cheaper than querying the db once per question.
            if answer.question_id == question.id:
                if question.variant == QuestionVariant.FILE:
                    return answer.answer_file, answer
                return answer.answer, answer
    return question.default_answer, None


class QuestionsForm(CfPFormMixin, ReadOnlyFlag, forms.Form):
    class Media:
        js = [forms.Script("common/js/forms/character-limit.js", defer="")]
        css = {"all": ["common/css/forms/character-limit.css"]}

    def __init__(
        self,
        *args,
        event,
        submission=None,
        speaker=None,
        review=None,
        track=None,
        submission_type=None,
        target=QuestionTarget.SUBMISSION,
        for_reviewers=False,
        skip_limited_questions=False,
        **kwargs,
    ):
        self.event = event
        self.submission = submission
        self.speaker = speaker
        self.review = review
        self.track = track or getattr(submission, "track", None)
        self.submission_type = submission_type or getattr(
            submission, "submission_type", None
        )
        self.target_type = target
        self.for_reviewers = for_reviewers

        super().__init__(*args, **kwargs)

        self.queryset = active_questions(
            self.event,
            target=self.target_type,
            track=self.track,
            submission_type=self.submission_type,
            for_reviewers=self.for_reviewers,
            skip_limited=skip_limited_questions,
        )
        for question in self.queryset:
            self.fields[f"question_{question.pk}"] = build_question_field(
                question=question,
                target_object=self.target_object_for(question),
                read_only=self.read_only,
            )

    def target_object_for(self, question):
        return getattr(self, _TARGET_ATTR[question.target])

    @cached_property
    def speaker_fields(self):
        return [
            forms.BoundField(self, field, name)
            for name, field in self.fields.items()
            if field.question.target == QuestionTarget.SPEAKER
        ]

    @cached_property
    def submission_fields(self):
        return [
            forms.BoundField(self, field, name)
            for name, field in self.fields.items()
            if field.question.target == QuestionTarget.SUBMISSION
        ]

    def serialize_answers(self):
        return {
            f"question-{field.question.pk}": (
                field.answer.answer_string if getattr(field, "answer", None) else None
            )
            for field in self.fields.values()
        }

    def save(self, *, submission=None, speaker=None, review=None):
        """Persist all cleaned answers.

        ``submission`` / ``speaker`` / ``review`` provide parent objects
        only known after validation (e.g. creating a new submission). When
        given, they override the values passed to ``__init__`` for this
        call only; ``self`` is not mutated.
        """
        targets = {
            QuestionTarget.SUBMISSION: (
                submission if submission is not None else self.submission
            ),
            QuestionTarget.SPEAKER: (speaker if speaker is not None else self.speaker),
            QuestionTarget.REVIEWER: (review if review is not None else self.review),
        }
        for key, value in self.cleaned_data.items():
            field = self.fields[key]
            target_object = targets[field.question.target]
            if target_object is None:
                raise ValueError(
                    f"Cannot save answer to question {field.question.pk}: "
                    f"no {field.question.target} target object available."
                )
            field.answer = save_answer(
                question=field.question,
                value=value,
                existing=field.answer,
                target_object=target_object,
            )


class QuestionOrgaForm(ReadOnlyFlag, PretalxI18nModelForm):
    options = forms.FileField(
        label=_("Upload options"),
        help_text=_(
            "You can upload options here, one option per line. "
            "To use multiple languages, please upload a JSON file with a list of "
            "options:"
        )
        + ' <code>[{"en": "English", "de": "Deutsch"}, ...]</code>',
        required=False,
    )
    options_replace = forms.BooleanField(
        label=_("Replace existing options"),
        help_text=_(
            "If you upload new options, do you want to replace the existing ones? "
            "Please note that this will DELETE all existing responses to this custom field! "
            "If you do not check this, the uploaded options will be added to the "
            "existing ones, without adding duplicates."
        ),
        required=False,
    )

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.instance.event = event
        self.fields["icon"].required = False
        self.fields["identifier"].required = False
        if event.has_active_tracks:
            self.fields["tracks"].queryset = event.tracks.all()
        else:
            self.fields.pop("tracks")
        if not event.submission_types.count():
            self.fields.pop("submission_types")
        else:
            self.fields["submission_types"].queryset = event.submission_types.all()
        self.fields["limit_teams"].queryset = event.teams.all()

    def clean_options(self):
        # read uploaded file, return list of strings or list of i18n strings
        options = self.cleaned_data.get("options")
        if not options:
            return
        try:
            content = options.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            raise forms.ValidationError(_("Could not read file.")) from None

        try:
            options = json.loads(content)
            if not isinstance(options, list):
                raise TypeError(_("JSON file does not contain a list."))  # noqa: TRY301  -- caught as fallback to line-split
            if not all(isinstance(opt, dict) for opt in options):
                raise TypeError(_("JSON file does not contain a list of objects."))  # noqa: TRY301  -- caught as fallback to line-split
            return [LazyI18nString(data=opt) for opt in options]
        except (ValueError, TypeError):
            options = content.split("\n")
            return [opt.strip() for opt in options if opt.strip()]

    def clean(self):
        question_required = self.cleaned_data.get("question_required")
        # ``Question.clean()`` already enforces the deadline rule for
        # ``AFTER_DEADLINE``. The remaining checks here are form-only.
        if question_required in (QuestionRequired.OPTIONAL, QuestionRequired.REQUIRED):
            self.cleaned_data["deadline"] = None
        options = self.cleaned_data.get("options")
        options_replace = self.cleaned_data.get("options_replace")
        if options_replace and not options:
            self.add_error(
                "options_replace",
                forms.ValidationError(
                    _("You cannot replace options without uploading new ones.")
                ),
            )
        if self.cleaned_data.get("is_public"):
            self.cleaned_data.pop("limit_teams", None)

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        apply_uploaded_options(
            question=instance,
            options=self.cleaned_data.get("options"),
            replace=bool(self.cleaned_data.get("options_replace")),
        )
        return instance

    class Media:
        js = [forms.Script("orga/js/forms/question.js", defer="")]

    class Meta:
        model = Question
        fields = [
            "target",
            "identifier",
            "question",
            "help_text",
            "question_required",
            "deadline",
            "freeze_after",
            "variant",
            "is_public",
            "is_visible_to_reviewers",
            "icon",
            "tracks",
            "submission_types",
            "limit_teams",
            "contains_personal_data",
            "min_length",
            "max_length",
            "min_number",
            "max_number",
            "min_date",
            "max_date",
            "min_datetime",
            "max_datetime",
        ]
        widgets = {
            "deadline": HtmlDateTimeInput,
            "question_required": forms.RadioSelect(),
            "freeze_after": HtmlDateTimeInput,
            "min_datetime": HtmlDateTimeInput,
            "max_datetime": HtmlDateTimeInput,
            "min_date": HtmlDateInput,
            "max_date": HtmlDateInput,
            "tracks": EnhancedSelectMultiple,
            "submission_types": EnhancedSelectMultiple,
            "limit_teams": EnhancedSelectMultiple,
            "icon": IconSelect,
        }
        field_classes = {
            "variant": SafeModelChoiceField,
            "tracks": SafeModelMultipleChoiceField,
            "submission_types": SafeModelMultipleChoiceField,
            "limit_teams": SafeModelMultipleChoiceField,
        }


class AnswerOptionForm(ReadOnlyFlag, PretalxI18nModelForm):
    class Meta:
        model = AnswerOption
        fields = ["answer"]


class QuestionFilterForm(forms.Form):
    default_renderer = InlineFormRenderer

    role = forms.ChoiceField(
        choices=(
            ("", phrases.base.all_choices),
            ("accepted", _("Accepted or confirmed speakers")),
            ("confirmed", _("Confirmed speakers")),
        ),
        required=False,
        label=_("Recipients"),
        widget=EnhancedSelect,
    )
    track = SafeModelChoiceField(
        Track.objects.none(), required=False, widget=EnhancedSelect
    )
    submission_type = SafeModelChoiceField(
        SubmissionType.objects.none(), required=False, widget=EnhancedSelect
    )

    def __init__(self, *args, event, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.fields["submission_type"].queryset = SubmissionType.objects.filter(
            event=event
        )
        if event.has_active_tracks:
            self.fields["track"].queryset = event.tracks.all()
        else:
            self.fields.pop("track", None)

    def get_submissions(self):
        role = self.cleaned_data["role"]
        track = self.cleaned_data.get("track")
        submission_type = self.cleaned_data["submission_type"]
        talks = self.event.submissions.all()
        if role == "accepted":
            talks = talks.filter(state__in=list(SubmissionStates.accepted_states))
        elif role == "confirmed":
            talks = talks.filter(state=SubmissionStates.CONFIRMED)
        if track:
            talks = talks.filter(track=track)
        if submission_type:
            talks = talks.filter(submission_type=submission_type)
        return talks

    def get_question_information(self, question):
        talks = self.get_submissions()
        speakers = self.event.submitters.filter(submissions__in=talks)
        return question_answer_summary(
            question=question, talks=talks, speakers=speakers
        )

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}


class ReminderFilterForm(QuestionFilterForm):
    questions = SafeModelMultipleChoiceField(
        Question.objects.none(),
        required=False,
        help_text=_("If you select no custom field, all will be used."),
        label=phrases.cfp.custom_fields,
        widget=EnhancedSelectMultiple,
    )

    def get_question_queryset(self):
        # We want to exclude questions with "freeze after", the deadlines of which have passed
        return Question.objects.filter(
            event=self.event, target__in=["speaker", "submission"]
        ).exclude(freeze_after__lt=timezone.now())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["questions"].queryset = self.get_question_queryset()
