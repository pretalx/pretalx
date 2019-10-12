import copy
import json
from collections import OrderedDict
from contextlib import contextmanager

from django import forms
from django.utils.translation import activate, gettext, get_language
from i18nfield.strings import LazyI18nString
from i18nfield.utils import I18nJSONEncoder

from pretalx.common.mixins.forms import QuestionFieldsMixin
from pretalx.common.forms.utils import validate_field_length



@contextmanager
def language(temporary_language):
    original_language = get_language()
    activate(temporary_language)
    try:
        yield
    finally:
        activate(original_language)


MARKDOWN_SUPPORT = {
    "submission_abstract", "submission_description", "submission_notes", "profile_biography",
}

DEFAULT_CFP_STEPS = {
    "event": None,
    "steps": [
        {
            "title": "Hey, nice to meet you!",  # TODO: i18n
            "text": "We're glad that you want to contribute to our event with your submission. Let's get started, this won't take long.",
            "icon": "paper-plane",
            "icon_label": "General",
            "fields": [
                {
                    "field_type": "submission",
                    "field_source": "title",
                    "required": True,
                },
                {
                    "field_type": "submission",
                    "field_source": "submission_type",
                    "required": True,
                },
                {
                    "field_type": "submission",
                    "field_source": "abstract",
                    "required": True,
                },
                {
                    "field_type": "submission",
                    "field_source": "description",
                    "required": False,
                },
                {
                    "field_type": "submission",
                    "field_source": "notes",
                    "required": False,
                },
                # {
                #     "field_type": "submission",
                #     "field_source": "additional_speakers",  # TODO: additional_speakers
                #     "required": False,
                # },
            ],
        },
        {
            "title": "That's it about your submission! We now just need a way to contact you.",  # TODO: i18n
            "text": "To create your submission, you need an account on this page. This not only gives us a way to contact you, it also gives you the possibility to edit your submission or to view its current state.",
            "icon": "user-circle-o",
            "icon_label": "Account",
            "identifier": "auth",
        },
        {
            "title": "Tell us something about yourself!",  # TODO: i18n
            "text": "This information will be publicly displayed next to your talk - you can always edit for as long as submissions are still open.",
            "icon": "address-card-o",
            "icon_label": "Profile",
            "fields": [
                {
                    "field_type": "user",
                    "field_source": "name",
                    "required": True,
                },
                {
                    "field_type": "profile",
                    "field_source": "biography",
                    "required": False,
                },
                # {
                #     "field_type": "profile",
                #     "field_source": "avatar", # TODO: get_gravatar combination
                #     "required": False,
                # },
            ],
        },
    ]
}


class CfPWorkflowForm(QuestionFieldsMixin, forms.Form):

    def __init__(self, *args, fields, event, user=None, **kwargs):
        self.event = event
        self.speaker = self.request_user = user
        super().__init__(*args, **kwargs)
        initial = kwargs.get('initial', dict())
        for field in fields:
            field_name, field = getattr(self, f"build_{field['field_type']}_field")(field, initial=initial)
            self.fields[field_name] = field

    def save_questions(self):
        for key, value in self.cleaned_data.items():
            if key.startswith('question_'):
                self.save_question(key, value)

    def get_cleaned_data(self, prefix):
        return {
            key[len(prefix) + 1:]: value
            for key, value in self.cleaned_data.items()
            if key.startswith(prefix + '_')
        }

    def build_model_field(self, field_data, initial, model):
        field_source = field_data["field_source"]
        field_type = field_data["field_type"]
        field_name = f"{field_type}_{field_source}"
        initial = initial.get(field_name)
        min_length = field_data.get("min_length")
        max_length = field_data.get("max_length")
        kwargs = {
            key: value
            for key, value in field_data.items()
            if key in ['help_text', 'required'] and value is not None
        }
        if initial is not None:
            kwargs['initial'] = initial
        help_text = get_help_text(
            kwargs.get("help_text", ""),
            min_length=field_data.get("min_length"),
            max_length=field_data.get("max_length"),
            count_in=self.event.settings.cfp_count_in,
        )
        if field_name in MARKDOWN_SUPPORT:
            help_text += " " + str(phrases.base.markdown)
            help_text = help_text.strip()
        kwargs["help_text"] = help_text
        field = model._meta.get_field(field_source).formfield(**kwargs)
        if min_length or max_length:
            field.validators.append(
                partial(
                    validate_field_length,
                    min_length=min_length,
                    max_length=max_length,
                    count_in=self.event.settings.cfp_count_length_in,
                )
            )
        # TODO: data migration from current model to this one
        return field_name, field

    def build_profile_field(self, field_data, initial):
        from pretalx.person.models import SpeakerProfile
        return self.build_model_field(field_data, initial, SpeakerProfile)

    def build_user_field(self, field_data, initial):
        from pretalx.person.models import User
        return self.build_model_field(field_data, initial, User)

    def build_submission_field(self, field_data, initial):
        from pretalx.submission.models import Submission
        return self.build_model_field(field_data, initial, Submission)

    def build_question_field(self, field_data, initial):
        question = self.event.questions.get(pk=field_data["question_pk"])
        field_name = f'question_{question.pk}'
        field = self.get_field(
            question, initial=initial.get(field_name), initial_object=None,
            readonly=False,
        )
        return field_name, field


def i18n_string(data, locales):
    if isinstance(data, str):
        data = {"en": str(data)}
    if not isinstance(data, dict):
        data = {"en": ""}

    english = data.get("en", "")
    for locale in locales:
        if locale not in data:
            with language(locale):
                data[locale] = gettext(english)
    return LazyI18nString(data)


class CfPWorkflow:
    steps = []
    event = None

    def __init__(self, data, event):
        self.event = event
        if isinstance(data, str) and data:
            data = json.loads(data)
        elif not isinstance(data, dict):
            data = copy.deepcopy(DEFAULT_CFP_STEPS)
        locales = self.event.locales
        for step in data["steps"]:
            for key in ("title", "text", "icon_label"):
                step[key] = i18n_string(step.get(key), locales)
            for field in step.get("fields", []):
                field["help_text"] = i18n_string(field.get("help_text"), locales)
        self.steps = data["steps"]
        self.steps_dict = {
            step.get('identifier', str(index)): step
            for index, step in enumerate(self.steps)
        }

    def get_form_list(self):
        from pretalx.person.forms import UserForm
        return OrderedDict([
            (
                step.get('identifier', str(index)),
                UserForm if step.get('identifier') == 'auth' else CfPWorkflowForm
            )
            for index, step in enumerate(self.steps)
        ])

    def all_data(self):
        return {
            "event": self.event.slug,
            "steps": self.steps,
        }

    @staticmethod
    def data(self):
        """Returns the canonical CfPWorkflow data format.
        Each step contains a 'title', a 'text', an 'icon', an 'icon_label', and
        a 'fields' list.
        The login/register form has instead an 'identifier', which is 'auth'.

        All fields will have:
            - A field_source, one of submission, user, profile, or question
            - For the types submission, user, and profile: a field_name
            - For the question type: a question_pk
            - The keys help_text and required"""
        return json.dumps(self.all_data(), cls=I18nJSONEncoder)

    def to_json(self):
        return self.data(self)

    def json_safe_data(self):
        return json.loads(self.to_json())

    def save(self):
        self.event.settings.cfp_workflow = self.to_json()
