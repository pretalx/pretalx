# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from functools import partial

import dateutil.parser
from django import forms
from django.utils.functional import cached_property

from pretalx.common.forms.fields import ExtensionFileField
from pretalx.common.forms.mixins import CfPFormMixin, ReadOnlyFlag, RequestRequire
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
)
from pretalx.submission.domain.queries.question import active_questions
from pretalx.submission.domain.question import save_answer
from pretalx.submission.models import QuestionTarget, QuestionVariant

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
        initial=dateutil.parser.parse(initial).date() if initial else None,
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
            dateutil.parser.parse(initial).astimezone(question.event.tz)
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
    from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- slow import
        rich_text,
    )

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

        ``submission`` / ``speaker`` / ``review`` override the parent objects
        passed at ``__init__``. Use them when the parent is only known after
        validation (e.g. creating a new submission).
        """
        if submission is not None:
            self.submission = submission
        if speaker is not None:
            self.speaker = speaker
        if review is not None:
            self.review = review
        for key, value in self.cleaned_data.items():
            field = self.fields[key]
            field.answer = save_answer(
                question=field.question,
                value=value,
                existing=field.answer,
                target_object=self.target_object_for(field.question),
            )
