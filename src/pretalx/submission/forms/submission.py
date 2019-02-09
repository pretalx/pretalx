import os

from django import forms
from django.conf import settings
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretalx.common.forms.fields import IMAGE_EXTENSIONS
from pretalx.common.forms.widgets import CheckboxMultiDropdown
from pretalx.common.mixins.forms import PublicContent, RequestRequire
from pretalx.submission.models import Submission, SubmissionStates


class InfoForm(RequestRequire, PublicContent, forms.ModelForm):
    additional_speaker = forms.EmailField(
        label=_('Additional Speaker'),
        help_text=_('If you have a co-speaker, please add their email address here, and we will invite them to create an account. If you have more than one co-speaker, you can add more speakers after finishing the submission process.'),
        required=False,
    )

    def __init__(self, event, **kwargs):
        self.event = event
        self.readonly = kwargs.pop('readonly', False)
        instance = kwargs.get('instance')
        initial = kwargs.pop('initial', {})
        initial['submission_type'] = getattr(
            instance, 'submission_type', self.event.cfp.default_type
        )
        initial['content_locale'] = getattr(
            instance, 'content_locale', self.event.locale
        )

        super().__init__(initial=initial, **kwargs)

        if 'abstract' in self.fields:
            self.fields['abstract'].widget.attrs['rows'] = 2
        if 'track' in self.fields:
            if not event.settings.use_tracks:
                self.fields.pop('track')
            elif not instance or instance.state == SubmissionStates.SUBMITTED:
                self.fields['track'].queryset = event.tracks.all()
            elif instance and instance.state != SubmissionStates.SUBMITTED:
                self.fields.pop('track')
        if instance and instance.pk:
            self.fields.pop('additional_speaker')

        self._set_submission_types(instance=instance)

        if len(self.event.locales) == 1:
            self.fields['content_locale'].initial = self.event.locales[0]
            self.fields['content_locale'].widget = forms.HiddenInput()
            self.fields['content_locale'].disabled = True
        else:
            locale_names = dict(settings.LANGUAGES)
            self.fields['content_locale'].choices = [
                (a, locale_names[a]) for a in self.event.locales
            ]

        if 'slot_count' in self.fields:
            if not event.settings.allow_slot_count:
                self.fields.pop('slot_count')
            else:
                # changes only allowed if not accepted or confirmed allready.
                if instance and (
                        instance.state == SubmissionStates.ACCEPTED or
                        instance.state == SubmissionStates.CONFIRMED):
                    self.fields['slot_count'].disabled = True
                    self.fields['slot_count'].help_text += (
                        _(' Locked - for changing see ') +
                        '<a href="#change_info">' +
                        str(_('this information')) +
                        '</a>.'
                    )

        if self.readonly:
            for f in self.fields.values():
                f.disabled = True

    def _set_submission_types(self, instance=None):
        _now = now()
        if (
            not self.event.cfp.deadline or self.event.cfp.deadline >= _now
        ):  # No global deadline or still open
            types = self.event.submission_types.exclude(deadline__lt=_now)
        else:
            types = self.event.submission_types.filter(deadline__gte=_now)
        pks = set(types.values_list('pk', flat=True))
        if instance and instance.pk:
            pks |= {instance.submission_type.pk}
        if len(pks) == 1:
            self.fields['submission_type'].initial = self.event.submission_types.get(pk=pks.pop())
            self.fields['content_locale'].widget = forms.HiddenInput()
            self.fields['content_locale'].disabled = True
        else:
            self.fields['submission_type'].queryset = self.event.submission_types.filter(
                pk__in=pks
            )

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            extension = os.path.splitext(image.name)[1].lower()
            if extension not in IMAGE_EXTENSIONS:
                raise forms.ValidationError(
                    _(
                        "This filetype is not allowed, it has to be one of the following: "
                    )
                    + ', '.join(IMAGE_EXTENSIONS)
                )
        return image

    class Meta:
        model = Submission
        fields = [
            'title',
            'submission_type',
            'track',
            'content_locale',
            'abstract',
            'description',
            'notes',
            'slot_count',
            'do_not_record',
            'image',
        ]
        request_require = [
            'abstract',
            'description',
            'notes',
            'image',
            'do_not_record',
            'track',
        ]
        public_fields = ['title', 'abstract', 'description', 'image']


class SubmissionFilterForm(forms.Form):
    state = forms.MultipleChoiceField(
        choices=SubmissionStates.get_choices(),
        required=False,
        widget=CheckboxMultiDropdown,
    )
    submission_type = forms.MultipleChoiceField(
        required=False, widget=CheckboxMultiDropdown
    )

    def __init__(self, event, *args, **kwargs):
        self.event = event
        usable_states = kwargs.pop('usable_states', None)
        super().__init__(*args, **kwargs)
        sub_count = (
            lambda x: event.submissions(manager='all_objects').filter(state=x).count()
        )  # noqa
        type_count = (
            lambda x: event.submissions(manager='all_objects')
            .filter(submission_type=x)  # noqa
            .count()
        )
        self.fields['submission_type'].choices = [
            (sub_type.pk, f'{str(sub_type)} ({type_count(sub_type.pk)})')
            for sub_type in event.submission_types.all()
        ]
        self.fields['submission_type'].widget.attrs['title'] = _('Submission types')
        if usable_states:
            usable_states = [
                choice
                for choice in self.fields['state'].choices
                if choice[0] in usable_states
            ]
        else:
            usable_states = self.fields['state'].choices
        self.fields['state'].choices = [
            (choice[0], f'{choice[1].capitalize()} ({sub_count(choice[0])})')
            for choice in usable_states
        ]
        self.fields['state'].widget.attrs['title'] = _('Submission states')
