from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from pretalx.mail.models import QueuedMail
from pretalx.submission.models import (
    Answer, QuestionVariant, Submission, SubmissionType,
)


class InfoForm(forms.ModelForm):

    def __init__(self, event, **kwargs):
        self.event = event
        readonly = kwargs.pop('readonly', False)

        super().__init__(**kwargs)
        self.fields['submission_type'].queryset = SubmissionType.objects.filter(event=self.event)
        locale_names = dict(settings.LANGUAGES)
        self.fields['content_locale'].choices = [(a, locale_names[a]) for a in self.event.locales]
        if readonly:
            for f in self.fields.values():
                f.disabled = True

    class Meta:
        model = Submission
        fields = [
            'title', 'submission_type', 'content_locale', 'abstract',
            'description', 'notes', 'do_not_record',
        ]


class QuestionsForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.submission = kwargs.pop('submission', None)
        self.speaker = kwargs.pop('speaker', None)
        self.request_user = kwargs.pop('request_user', None)
        self.target_type = kwargs.pop('target', 'submission')
        target_object = self.submission or self.speaker if self.target_type else None
        readonly = kwargs.pop('readonly', False)

        super().__init__(*args, **kwargs)

        queryset = self.event.questions.filter(active=True)
        if self.target_type:
            queryset = queryset.filter(target=self.target_type)
        for question in queryset.prefetch_related('options'):
            if target_object:
                answers = [a for a in target_object.answers.all() if a.question_id == question.id]
                if answers:
                    initial_object = answers[0]
                    initial = answers[0].answer_file if question.variant == QuestionVariant.FILE else answers[0].answer
                else:
                    initial_object = None
                    initial = question.default_answer
            else:
                initial_object = None
                initial = question.default_answer

            field = self.get_field(question=question, initial=initial, initial_object=initial_object, readonly=readonly)
            field.question = question
            field.answer = initial_object
            self.fields[f'question_{question.pk}'] = field

    @cached_property
    def speaker_fields(self):
        return [forms.BoundField(self, field, name) for name, field in self.fields.items() if field.question.target == 'speaker']

    @cached_property
    def submission_fields(self):
        return [forms.BoundField(self, field, name) for name, field in self.fields.items() if field.question.target == 'submission']

    def get_field(self, *, question, initial, initial_object, readonly):
        if question.variant == QuestionVariant.BOOLEAN:
            # For some reason, django-bootstrap4 does not set the required attribute
            # itself.
            widget = forms.CheckboxInput(attrs={'required': 'required'}) if question.required else forms.CheckboxInput()
            initialbool = (initial == 'True') if initial else bool(question.default_answer)

            return forms.BooleanField(
                disabled=readonly, help_text=question.help_text,
                label=question.question, required=question.required,
                widget=widget, initial=initialbool
            )
        elif question.variant == QuestionVariant.NUMBER:
            return forms.DecimalField(
                disabled=readonly, help_text=question.help_text,
                label=question.question, required=question.required,
                min_value=Decimal('0.00'), initial=initial
            )
        elif question.variant == QuestionVariant.STRING:
            return forms.CharField(
                disabled=readonly, help_text=question.help_text,
                label=question.question, required=question.required, initial=initial
            )
        elif question.variant == QuestionVariant.TEXT:
            return forms.CharField(
                label=question.question, required=question.required,
                widget=forms.Textarea,
                disabled=readonly, help_text=question.help_text,
                initial=initial
            )
        elif question.variant == QuestionVariant.FILE:
            return forms.FileField(
                label=question.question, required=question.required,
                disabled=readonly, help_text=question.help_text,
                initial=initial
            )
        elif question.variant == QuestionVariant.CHOICES:
            return forms.ModelChoiceField(
                queryset=question.options.all(),
                label=question.question, required=question.required,
                initial=initial_object.options.first() if initial_object else question.default_answer,
                disabled=readonly, help_text=question.help_text,
            )
        elif question.variant == QuestionVariant.MULTIPLE:
            return forms.ModelMultipleChoiceField(
                queryset=question.options.all(),
                label=question.question, required=question.required,
                widget=forms.CheckboxSelectMultiple,
                initial=initial_object.options.all() if initial_object else question.default_answer,
                disabled=readonly, help_text=question.help_text,
            )

    def save(self):
        for k, v in self.cleaned_data.items():
            field = self.fields[k]
            if field.answer:
                # We already have a cached answer object, so we don't
                # have to create a new one
                if v == '':
                    # TODO: Deleting the answer removes the option to have a log here.
                    # Maybe setting the answer to '' is the right way to go.
                    field.answer.delete()
                else:
                    self._save_to_answer(field, field.answer, v)
                    field.answer.save()
            elif v != '':
                # Not distinguishing between the question types helps to make
                # experiences smoother if orga changes a question type.
                answer = Answer(
                    submission=self.submission,
                    person=self.speaker,
                    question=field.question,
                )
                self._save_to_answer(field, answer, v)
                answer.save()

    def _save_to_answer(self, field, answer, value):
        action = 'pretalx.submission.answer' + ('update' if answer.pk else 'create')
        if isinstance(field, forms.ModelMultipleChoiceField):
            answstr = ', '.join([str(o) for o in value])
            if not answer.pk:
                answer.save()
            else:
                answer.options.clear()
            answer.answer = answstr
            answer.options.add(*value)
        elif isinstance(field, forms.ModelChoiceField):
            if not answer.pk:
                answer.save()
            else:
                answer.options.clear()
            answer.options.add(value)
            answer.answer = value.answer
        elif isinstance(field, forms.FileField):
            if isinstance(value, UploadedFile):
                answer.answer_file.save(value.name, value)
                answer.answer = 'file://' + value.name
                value = answer.answer
        else:
            answer.answer = value
        answer.log_action(action, person=self.request_user, data={'answer': value})


class SubmissionInvitationForm(forms.Form):
    speaker = forms.EmailField(label=_('Speaker E-Mail'))
    subject = forms.CharField(label=_('Subject'))
    text = forms.CharField(widget=forms.Textarea(), label=_('Text'))

    def __init__(self, submission, speaker, *args, **kwargs):
        self.submission = submission
        initial = kwargs.get('initial', {})
        initial['subject'] = _('[{event}] {speaker} invites you to join their talk!').format(
            event=submission.event.slug, speaker=speaker.name or speaker.nick,
        )
        initial['text'] = _('''Hi!

I'd like to invite you to be a speaker in my talk »{title}«
at {event}. Please follow this link to join:

  {url}

I'm looking forward to it!
{speaker}''').format(
            event=submission.event.name, title=submission.title,
            url=submission.urls.accept_invitation.full(scheme='https', hostname=settings.SITE_NETLOC),
            speaker=speaker.name or speaker.nick,
        )
        super().__init__(*args, **kwargs)

    def save(self):
        QueuedMail(
            event=self.submission.event,
            to=self.cleaned_data['speaker'],
            subject=self.cleaned_data['subject'],
            text=self.cleaned_data['text'],
        ).send()
