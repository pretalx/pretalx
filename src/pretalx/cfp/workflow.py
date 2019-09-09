import copy
import json
from collections import OrderedDict

from django import forms

from pretalx.common.mixins.forms import QuestionFieldsMixin

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
            "icon": "paper-circle-o",
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
        kwargs = {
            key: value
            for key, value in field_data.items()
            if key in ['help_text', 'required'] and value is not None
        }
        if initial is not None:
            kwargs['initial'] = initial
        field = model._meta.get_field(field_source).formfield(**kwargs)
        # TODO: help_text with min_length, max_length, required
        # TODO: data migration from current model to this one
        # TODO: UI
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


class CfPWorkflow:
    steps = []
    event = None

    def __init__(self, data):
        from pretalx.event.models import Event
        if data:
            data = json.loads(data)
            self.event = Event.objects.get(slug__iexact=data["event"])
        else:
            data = copy.deepcopy(DEFAULT_CFP_STEPS)
            self.event = Event.objects.first()  # TODO: omg no
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

    def to_json(self):
        return self.data(self)

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
        return json.dumps({
            "event": self.event.slug,
            "steps": self.steps,
        })
