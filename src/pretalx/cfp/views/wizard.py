import logging
from collections import ChainMap, OrderedDict
from contextlib import suppress
from pathlib import Path

from csp.decorators import csp_update
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.forms import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from formtools.wizard.views import NamedUrlSessionWizardView

from pretalx.cfp.views.event import EventPageMixin
from pretalx.common.mail import SendMailException
from pretalx.common.mixins.views import SensibleBackWizardMixin
from pretalx.common.phrases import phrases
from pretalx.mail.context import template_context_from_submission
from pretalx.mail.models import MailTemplate
from pretalx.person.forms import UserForm
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import Submission, SubmissionType, Track

FORM_DATA = {
    'info': {'label': _('General'), 'icon': 'paper-plane'},
    'questions': {'label': _('Questions'), 'icon': 'question-circle-o'},
    'user': {'label': _('Account'), 'icon': 'user-circle-o'},
    'profile': {'label': _('Profile'), 'icon': 'address-card-o'},
}


class SubmitStartView(EventPageMixin, View):

    @staticmethod
    def get(request, *args, **kwargs):
        url = reverse(
            'cfp:event.submit',
            kwargs={
                'event': request.event.slug,
                'step': '0',
                'tmpid': get_random_string(length=6),
            },
        )
        if request.GET:
            url += f'?{request.GET.urlencode()}'
        return redirect(url)


def show_login_page(wizard):
    return not wizard.request.user.is_authenticated


@method_decorator(csp_update(IMG_SRC="https://www.gravatar.com"), name='dispatch')
class SubmitWizard(EventPageMixin, SensibleBackWizardMixin, NamedUrlSessionWizardView):
    condition_dict = {'auth': show_login_page}
    form_list = [UserForm]
    file_storage = FileSystemStorage(str(Path(settings.MEDIA_ROOT) / 'avatars'))

    def get_form_list(self):
        form_list = self.event.settings.cfp_workflow.get_form_list()
        result = OrderedDict()
        for form_key in form_list:
            condition = self.condition_dict.get(form_key, True)
            if callable(condition):
                condition = condition(self)
            if condition:
                result[form_key] = form_list[form_key]
        return result

    def dispatch(self, request, *args, **kwargs):
        self.event = request.event
        self.form_list = self.get_form_list()
        self.access_code = None
        if 'access_code' in request.GET:
            access_code = request.event.submitter_access_codes.filter(
                code__iexact=request.GET['access_code']
            ).first()
            if access_code and access_code.is_valid:
                self.access_code = access_code
        if not request.event.cfp.is_open and not self.access_code:
            messages.error(request, phrases.cfp.submissions_closed)
            return redirect(
                reverse('cfp:event.start', kwargs={'event': request.event.slug})
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        if step == 'auth':
            return kwargs
        kwargs['fields'] = self.event.settings.cfp_workflow.steps_dict[step]['fields']
        user_data = self.get_cleaned_data_for_step('auth') or dict()
        if user_data and user_data.get('user_id'):
            kwargs['user'] = User.objects.filter(pk=user_data['user_id']).first()
        if not kwargs.get('user') and self.request.user.is_authenticated:
            kwargs['user'] = self.request.user
        if step == 'info':
            kwargs['access_code'] = self.access_code
        return kwargs

    def get_form_initial(self, step):
        initial = super().get_form_initial(step)
        for field, model in (('submission_type', SubmissionType), ('track', Track)):
            request_value = self.request.GET.get(field)
            if request_value:
                with suppress(AttributeError, TypeError):
                    pk = int(request_value.split('-'))
                    obj = model.objects.filter(event=self.request.event, pk=pk).first()
                    if obj:
                        initial[field] = obj
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        step = kwargs.get('step')
        step_list = []
        phase = 'done'
        for stp, form_class in self.get_form_list().items():
            if stp == step:
                phase = 'current'
            step_list.append(
                {
                    'url': self.get_step_url(stp),
                    'phase': phase,
                    'label': self.event.settings.cfp_workflow.steps_dict[stp]['icon_label'],
                    'icon': self.event.settings.cfp_workflow.steps_dict[stp]['icon'],
                }
            )
            if phase == 'current':
                phase = 'todo'
        step_list.append({'phase': 'todo', 'label': _('Done!'), 'icon': 'check'})
        context['step_list'] = step_list

        step_info = self.event.settings.cfp_workflow.steps_dict[step]
        context['step_title'] = step_info.get('title')
        context['step_text'] = step_info.get('text')

        if hasattr(self.request.user, 'email'):
            email = self.request.user.email
        else:
            data = self.get_cleaned_data_for_step('auth') or dict()
            email = data.get('register_email', '')
        if email:
            context['gravatar_parameter'] = User(email=email).gravatar_parameter
        return context

    def get_template_names(self):
        if self.steps.current == 'auth':
            return f'cfp/event/submission_user.html'
        return f'cfp/event/submission_step.html'

    def get_prefix(self, request, *args, **kwargs):
        return super().get_prefix(request, *args, **kwargs) + ':' + kwargs.get('tmpid')

    def get_step_url(self, step):
        url = reverse(
            self.url_name,
            kwargs={
                'step': step,
                'tmpid': self.kwargs.get('tmpid'),
                'event': self.kwargs.get('event'),
            },
        )
        if self.request.GET:
            url += f'?{self.request.GET.urlencode()}'
        return url

    @transaction.atomic
    def done(self, form_list, **kwargs):
        form_dict = kwargs.get('form_dict')
        auth_form = form_dict.pop('auth', None)
        if self.request.user.is_authenticated:
            user = self.request.user
        else:
            uid = auth_form.save()
            user = User.objects.filter(pk=uid).first()
        if not user or not user.is_active:
            raise ValidationError(
                _(
                    'There was an error when logging in. Please contact the organiser for further help.'
                ),
            )
        sub = Submission.objects.create(
            event=self.request.event,
            **ChainMap(*[form.get_cleaned_data('submission') for form in form_dict.values()])
        )
        sub.speakers.add(user)
        SpeakerProfile.objects.create(
            user=user, event=self.event,
            **ChainMap(*[form.get_cleaned_data('profile') for form in form_dict.values()])
        )
        for form in form_dict.values():
            form.submission = sub
            form.request_user = user
            form.speaker = user
            form.save_questions()

        try:
            sub.event.ack_template.to_mail(
                user=user,
                event=self.request.event,
                context=template_context_from_submission(sub),
                skip_queue=True,
                locale=user.locale,
                submission=sub,
                full_submission_content=True,
            )
            if self.request.event.settings.mail_on_new_submission:
                MailTemplate(
                    event=self.request.event,
                    subject=_('New submission!').format(event=self.request.event.slug),
                    text=self.request.event.settings.mail_text_new_submission,
                ).to_mail(
                    user=self.request.event.email,
                    event=self.request.event,
                    context=template_context_from_submission(sub),
                    skip_queue=True,
                    locale=self.request.event.locale,
                )
            # additional_speaker = form_dict['info'].cleaned_data.get('additional_speaker').strip()  # TODO: additional_speaker
            # if additional_speaker:
            #    sub.send_invite(to=[additional_speaker], _from=user)
        except SendMailException as exception:
            logging.getLogger('').warning(str(exception))
            messages.warning(self.request, phrases.cfp.submission_email_fail)

        if self.access_code:
            sub.access_code = self.access_code
            sub.save()
            self.access_code.redeemed += 1
            self.access_code.save()

        sub.log_action('pretalx.submission.create', person=user)
        messages.success(self.request, phrases.cfp.submission_success)
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(
            reverse(
                'cfp:event.user.submissions', kwargs={'event': self.request.event.slug}
            )
        )
