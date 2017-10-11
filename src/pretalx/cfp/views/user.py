from csp.decorators import csp_update
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    DetailView, ListView, TemplateView, UpdateView, View,
)

from pretalx.cfp.forms.submissions import InfoForm, QuestionsForm
from pretalx.cfp.views.event import LoggedInEventPageMixin
from pretalx.person.forms import LoginInfoForm, SpeakerProfileForm
from pretalx.submission.models import Submission, SubmissionStates


@method_decorator(csp_update(STYLE_SRC="'self' 'unsafe-inline'"), name='dispatch')
class ProfileView(LoggedInEventPageMixin, TemplateView):
    template_name = 'cfp/event/user_profile.html'

    @cached_property
    def login_form(self):
        return LoginInfoForm(user=self.request.user,
                             data=(self.request.POST
                                   if self.request.method == 'POST'
                                   and self.request.POST.get('form') == 'login'
                                   else None))

    @cached_property
    def profile_form(self):
        if self.request.method == 'POST' and self.request.POST.get('form') == 'profile':
            return SpeakerProfileForm(
                user=self.request.user,
                event=self.request.event,
                read_only=False,
                data=self.request.POST,
                files=self.request.FILES,
            )
        return SpeakerProfileForm(
            user=self.request.user,
            event=self.request.event,
            read_only=False,
            data=None,
        )

    @cached_property
    def questions_form(self):
        return QuestionsForm(
            data=self.request.POST if self.request.method == 'POST' else None,
            speaker=self.request.user,
            event=self.request.event,
            target='speaker',
            request_user=self.request.user,
        )

    def get_context_data(self, event):
        ctx = super().get_context_data()
        ctx['login_form'] = self.login_form
        ctx['profile_form'] = self.profile_form
        ctx['questions_form'] = self.questions_form
        ctx['questions_exist'] = self.request.event.questions.filter(target='speaker').exists()
        return ctx

    def post(self, request, *args, **kwargs):
        if self.login_form.is_bound:
            if self.login_form.is_valid():
                self.login_form.save()
                messages.success(self.request, _('Your changes have been saved.'))
                request.user.log_action('pretalx.user.password.update', person=request.user)
                return redirect('cfp:event.user.view', event=self.request.event.slug)
        elif self.profile_form.is_bound:
            if self.profile_form.is_valid():
                self.profile_form.save()
                messages.success(self.request, _('Your changes have been saved.'))
                profile = self.request.user.profiles.get_or_create(event=self.request.event)[0]
                profile.log_action('pretalx.user.profile.update', person=request.user)
                return redirect('cfp:event.user.view', event=self.request.event.slug)
        elif self.questions_form.is_bound:
            if self.questions_form.is_valid():
                self.questions_form.save()
                messages.success(self.request, _('Your changes have been saved.'))
                return redirect('cfp:event.user.view', event=self.request.event.slug)

        messages.error(self.request, _('Oh :( We had trouble saving your input. See below for details.'))
        return super().get(request, *args, **kwargs)


class SubmissionViewMixin:
    def get_object(self):
        try:
            return self.request.event.submissions.prefetch_related('answers', 'answers__options').get(
                speakers__in=[self.request.user],
                code=self.kwargs.get('code')
            )
        except Submission.DoesNotExist:
            try:
                # Backwards compatibility
                return self.request.event.submissions.prefetch_related('answers', 'answers__options').get(
                    speakers__in=[self.request.user],
                    id=self.kwargs.get('code')
                )
            except (Submission.DoesNotExist, ValueError):
                raise Http404()


class SubmissionsListView(LoggedInEventPageMixin, ListView):
    template_name = 'cfp/event/user_submissions.html'
    context_object_name = 'submissions'

    def get_queryset(self):
        return self.request.event.submissions.filter(speakers__in=[self.request.user])


class SubmissionsWithdrawView(LoggedInEventPageMixin, SubmissionViewMixin, DetailView):
    template_name = 'cfp/event/user_submission_withdraw.html'
    model = Submission
    context_object_name = 'submission'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.state == SubmissionStates.SUBMITTED:
            self.object.state = SubmissionStates.WITHDRAWN
            self.object.save(update_fields=['state'])
            self.object.log_action('pretalx.submission.withdrawal', person=request.user)
            messages.success(self.request, _('Your submission has been withdrawn.'))
        else:
            messages.error(self.request, _('Your submission can\'t be withdrawn at this time – please contact us if you need to withdraw your submission!'))
        return redirect('cfp:event.user.submissions', event=self.request.event.slug)


class SubmissionConfirmView(LoggedInEventPageMixin, SubmissionViewMixin, View):

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect(request.event.urls.login)
        submission = self.get_object()
        if submission.state == SubmissionStates.ACCEPTED:
            submission.confirm(person=request.user, orga=False)
            messages.success(self.request, _('Your submission has been confirmed – we\'re looking forward to seeing you!'))
        elif submission.state == SubmissionStates.CONFIRMED:
            messages.success(self.request, _('This submission has already been confirmed – we\'re looking forward to seeing you!'))
        else:
            messages.error(self.request, _('This submission cannot be confirmed at this time – please contact us if you think this is an error.'))
        return redirect('cfp:event.user.submissions', event=self.request.event.slug)


class SubmissionsEditView(LoggedInEventPageMixin, SubmissionViewMixin, UpdateView):
    template_name = 'cfp/event/user_submission_edit.html'
    model = Submission
    form_class = InfoForm
    context_object_name = 'submission'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['qform'] = self.qform
        ctx['can_edit'] = self.can_edit
        return ctx

    @cached_property
    def qform(self):
        return QuestionsForm(
            data=self.request.POST if self.request.method == 'POST' else None,
            submission=self.object,
            event=self.request.event,
            readonly=not self.can_edit,
        )

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid() and self.qform.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @property
    def can_edit(self):
        return self.object.editable

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        kwargs['readonly'] = not self.can_edit
        return kwargs

    def form_valid(self, form):
        if self.can_edit:
            form.save()
            self.qform.save()
            if form.has_changed():
                form.instance.log_action('pretalx.submission.update', person=self.request.user)
            messages.success(self.request, _('Your changes have been saved.'))
        else:
            messages.error(self.request, _('This submission cannot be edited anymore.'))
        return redirect('cfp:event.user.submissions', event=self.request.event.slug)


class DeleteAccountView(View):

    def post(self, request, event):

        if request.POST.get('really'):
            from django.contrib.auth import logout
            request.user.deactivate()
            logout(request)
            messages.success(request, _('Your account has now been deleted.'))
            return redirect(request.event.urls.base)
        else:
            messages.error(request, _('Are you really sure? Please tick the box'))
            return redirect(request.event.urls.user + '?really')
