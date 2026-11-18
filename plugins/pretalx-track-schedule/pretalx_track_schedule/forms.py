import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.submission.models import Question

from .colors import CHOICE_VARIANTS
from .models import ColorSettings, OptionColor, default_color

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class ColorInput(forms.TextInput):
    input_type = "color"


class ColorSettingsForm(forms.Form):
    """The question to colour by, and one colour per option of the question
    currently chosen (after picking another question, save to get its
    colours)."""

    question = SafeModelChoiceField(
        # Set per event in __init__; this field type is safe outside a scope
        queryset=Question.objects.none(),
        required=False,
        label=_("Colour sessions by"),
        empty_label=_("Track (no question)"),
        help_text=_(
            "A choice question asked per proposal, such as difficulty. Sessions "
            "without an answer keep their track colour."
        ),
    )

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        questions = (
            event.questions(manager="all_objects")
            .filter(target="submission", variant__in=CHOICE_VARIANTS)
            .order_by("position", "id")
        )
        self.fields["question"].queryset = questions
        self.settings = ColorSettings.objects.filter(event=event).first()
        current = self.settings.question if self.settings else None
        if current is None:
            # Suggest a difficulty question, if there is one
            current = next(
                (q for q in questions if "difficult" in str(q.question).lower()), None
            )
        self.fields["question"].initial = current
        self.options = (
            list(current.options.all().order_by("position", "id")) if current else []
        )
        saved = {
            oc.option_id: oc.color
            for oc in OptionColor.objects.filter(option__in=self.options)
        }
        for index, option in enumerate(self.options):
            self.fields[f"color_{option.pk}"] = forms.CharField(
                label=str(option.answer),
                initial=saved.get(option.pk) or default_color(option, index),
                widget=ColorInput(),
                max_length=7,
                # Left out (e.g. when only the question is changed): keep it
                required=False,
            )

    def clean(self):
        data = super().clean()
        for name, value in list(data.items()):
            if not name.startswith("color_"):
                continue
            if not value:
                data[name] = self.fields[name].initial
            elif not HEX.match(value):
                self.add_error(name, ValidationError(_("Use a colour like #2e9d4f.")))
        return data

    def save(self):
        question = self.cleaned_data["question"]
        ColorSettings.objects.update_or_create(
            event=self.event, defaults={"question": question}
        )
        if question is None:
            return None
        if self.options and self.options[0].question_id == question.pk:
            for option in self.options:
                OptionColor.objects.update_or_create(
                    option=option,
                    defaults={"color": self.cleaned_data[f"color_{option.pk}"].lower()},
                )
        else:
            # A newly chosen question: start with the default colours, so the
            # schedule is coloured right away
            for index, option in enumerate(
                question.options.all().order_by("position", "id")
            ):
                OptionColor.objects.get_or_create(
                    option=option, defaults={"color": default_color(option, index)}
                )
        return question
