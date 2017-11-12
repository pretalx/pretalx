from contextlib import suppress
from urllib.parse import urlparse

import vobject
from csp.decorators import csp_update
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.generic import DetailView, FormView

from pretalx.agenda.forms import FeedbackForm
from pretalx.cfp.views.event import EventPageMixin
from pretalx.common.mixins.views import PermissionRequired
from pretalx.common.phrases import phrases
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Feedback, Submission


class TalkView(PermissionRequired, DetailView):
    context_object_name = 'talk'
    model = Submission
    slug_field = 'code'
    template_name = 'agenda/talk.html'
    permission_required = 'agenda.view_slot'

    def get_object(self):
        with suppress(AttributeError, TalkSlot.DoesNotExist):
            return self.request.event.current_schedule.talks.get(submission__code__iexact=self.kwargs['slug'])
        raise Http404()

    @csp_update(CHILD_SRC="https://media.ccc.de")  # TODO: only do this if obj.recording_url and obj.recording_source are set
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        event_talks = self.request.event.current_schedule.talks.exclude(submission=self.object.submission)
        ctx['speakers'] = []
        for speaker in self.object.submission.speakers.all():  # TODO: there's bound to be an elegant annotation for this
            speaker.talk_profile = speaker.profiles.filter(event=self.request.event).first()
            speaker.other_talks = event_talks.filter(submission__speakers__in=[speaker])
            ctx['speakers'].append(speaker)
        return ctx


class SingleICalView(EventPageMixin, DetailView):
    model = Submission
    slug_field = 'code'

    def get(self, request, event, **kwargs):
        talk = self.get_object().slots.get(schedule=self.request.event.current_schedule)
        netloc = urlparse(settings.SITE_URL).netloc

        cal = vobject.iCalendar()
        cal.add('prodid').value = '-//pretalx//{}//{}'.format(netloc, talk.submission.code)
        talk.build_ical(cal)

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = f'attachment; filename="{request.event.slug}-{talk.submission.code}.ics"'
        return resp


class FeedbackView(PermissionRequired, FormView):
    model = Feedback
    form_class = FeedbackForm
    template_name = 'agenda/feedback_form.html'
    permission_required = 'agenda.give_feedback'

    def get_object(self):
        return Submission.objects.filter(
            event=self.request.event,
            code__iexact=self.kwargs['slug'],
            slots__in=self.request.event.current_schedule.talks.all(),
        ).first()

    def get(self, *args, **kwargs):
        obj = self.get_object()
        if obj and self.request.user in obj.speakers.all():
            return render(
                self.request,
                'agenda/feedback.html',
                context={
                    'talk': obj,
                    'feedback': obj.feedback.filter(Q(speaker__isnull=True) | Q(speaker=self.request.user)),
                }
            )
        return super().get(*args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['talk'] = self.get_object()
        return kwargs

    def get_context_data(self):
        ctx = super().get_context_data()
        ctx['talk'] = self.get_object()
        return ctx

    def form_valid(self, form):
        if not form.instance.talk.does_accept_feedback:
            return super().form_invalid(form)
        ret = super().form_valid(form)
        form.save()
        messages.success(self.request, phrases.agenda.feedback_success)
        return ret

    def get_success_url(self):
        return self.get_object().urls.public
