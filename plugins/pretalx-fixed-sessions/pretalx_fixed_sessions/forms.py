from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.common.forms.widgets import MarkdownWidget

from .models import FixedSession


class SpeakerChoiceSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.choices = [
            ("unknown", _("Speaker chooses")),
            ("true", _("Yes")),
            ("false", _("No")),
        ]


class FixedSessionForm(forms.ModelForm):
    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        tracks = event.tracks.all()
        if tracks.exists():
            self.fields["track"].queryset = tracks
        else:
            self.fields.pop("track")

    class Meta:
        model = FixedSession
        fields = ["title", "abstract", "description", "track", "do_not_record"]
        widgets = {
            "abstract": MarkdownWidget(attrs={"rows": 3}),
            "description": MarkdownWidget(),
            "do_not_record": SpeakerChoiceSelect(),
        }
        # Track is a scoped model: the default field would query it when this
        # class is defined, which fails outside an event scope
        field_classes = {"track": SafeModelChoiceField}


class NewFixedSessionForm(FixedSessionForm):
    """Creates the session type together with its fixed content."""

    name = forms.CharField(
        max_length=100,
        label=_("Session type name"),
        help_text=_("Shown to speakers when they choose a session type."),
    )
    default_duration = forms.IntegerField(
        min_value=1, initial=60, label=_("Duration"), help_text=_("Duration in minutes")
    )
    field_order = ["name", "default_duration"]

    def save(self, commit=True):
        from pretalx.submission.models import SubmissionType

        self.instance.submission_type = SubmissionType.objects.create(
            event=self.event,
            name=self.cleaned_data["name"],
            default_duration=self.cleaned_data["default_duration"],
        )
        return super().save(commit=commit)


class FixedAnswersForm(forms.Form):
    """One field per question asked per proposal, built by pretalx so it has
    the same widget and validation as in the CfP. Empty means the speaker
    answers. File questions can't be fixed."""

    prefix = "answers"

    def __init__(self, *args, event, submission_type=None, fixed=None, **kwargs):
        from pretalx.submission.domain.queries.question import active_questions
        from pretalx.submission.interfaces.forms.question import build_question_field
        from pretalx.submission.models import QuestionVariant

        super().__init__(*args, **kwargs)
        questions = active_questions(event, submission_type=submission_type).exclude(
            variant=QuestionVariant.FILE
        )
        if submission_type is None:
            # A new session type can't be among the types a question is limited to
            questions = questions.filter(submission_types__isnull=True)
        self.fixed = fixed if fixed is not None and fixed.pk else None
        existing = (
            {a.question_id: a for a in self.fixed.answers.all()} if self.fixed else {}
        )
        for question in questions:
            if question.variant == QuestionVariant.BOOLEAN:
                # Three states: pretalx's checkbox can't say "speaker answers"
                answer = existing.get(question.pk)
                field = forms.NullBooleanField(
                    widget=SpeakerChoiceSelect(),
                    initial=(answer.answer == "True") if answer else None,
                )
            else:
                # The fixed session stands in for the proposal: its answers
                # have the attributes pretalx reads the initial value from
                field = build_question_field(
                    question=question, target_object=self.fixed
                )
                if question.pk not in existing:
                    field.initial = None
                if question.variant == QuestionVariant.CHOICES:
                    field.empty_label = _("Speaker answers")
                    field.widget = forms.Select(choices=field.choices)
            field.label = question.question
            field.help_text = _("Leave empty to let the speaker answer.")
            field.required = False
            field.disabled = False
            field.question = question
            self.fields[f"question_{question.pk}"] = field

    def save(self, fixed):
        from pretalx.submission.models import QuestionVariant

        from .models import FixedAnswer

        for name, value in self.cleaned_data.items():
            question = self.fields[name].question
            if (
                value is None
                or value == ""
                or (question.variant == QuestionVariant.MULTIPLE and not value)
            ):
                FixedAnswer.objects.filter(
                    fixed_session=fixed, question=question
                ).delete()
                continue
            options = []
            if question.variant == QuestionVariant.CHOICES:
                options = [value]
            elif question.variant == QuestionVariant.MULTIPLE:
                options = list(value)
            # The same text pretalx stores in Answer.answer
            text = (
                ", ".join(str(option) for option in options) if options else str(value)
            )
            answer, _created = FixedAnswer.objects.update_or_create(
                fixed_session=fixed, question=question, defaults={"answer": text}
            )
            answer.options.set(options)
