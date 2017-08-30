from datetime import datetime, timedelta
from urllib.parse import urlparse

import pytz
import vobject
from csp.decorators import csp_update
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, TemplateView

from pretalx.cfp.views.event import EventPageMixin
from pretalx.submission.models import Submission, SubmissionStates


def day_start(dt):
    return dt.replace(hour=0, minute=0, second=0)


def day_end(dt):
    return dt.replace(hour=23, minute=59, second=59)


class ScheduleDataView(EventPageMixin, TemplateView):
    template_name = 'agenda/schedule.html'

    def get_object(self):
        if self.request.GET.get('version'):
            return self.request.event.schedules.filter(version=self.request.GET.get('version'))
        return self.request.event.current_schedule

    def get_context_data(self, event):
        ctx = super().get_context_data()
        schedule = self.get_object()
        event = self.request.event
        tz = pytz.timezone(self.request.event.timezone)

        if not schedule and self.request.GET.get('version'):
            ctx['version'] = self.request.GET.get('version')
            ctx['error'] = 'wrong-version'
            return ctx
        elif not schedule:
            ctx['error'] = 'no-schedule'
            return ctx
        ctx['schedule'] = schedule
        ctx['schedules'] = event.schedules.filter(published__isnull=False).values_list('version')

        talks = schedule.talks.filter(is_visible=True).select_related(
            'submission', 'submission__event', 'room'
        ).prefetch_related(
            'submission__speakers'
        ).order_by(
            'start'
        )
        rooms = event.rooms.all()

        ctx['data'] = [
            {
                'index': index + 1,
                'start': current_date,
                'end': current_date + timedelta(days=1),
                'first_start': min([t.start for t in talks if t.start.astimezone(tz).date() == current_date.date()] or [0]),
                'last_end': max([t.end for t in talks if t.start.astimezone(tz).date() == current_date.date()] or [0]),
                'rooms': [{
                    'name': room.name,
                    'talks': [talk for talk in talks
                              if talk.start.astimezone(tz).date() == current_date.date() and talk.room_id == room.pk],
                } for room in rooms],
            } for index, current_date in enumerate([
                event.datetime_from + timedelta(days=i) for i in range((event.date_to - event.date_from).days + 1)
            ])
        ]
        return ctx


@method_decorator(csp_update(STYLE_SRC="'self' 'unsafe-inline'"), name='dispatch')
class ScheduleView(ScheduleDataView):
    template_name = 'agenda/schedule.html'

    def get_object(self):
        obj = super().get_object()
        if not obj and self.request.is_orga:
            return self.request.event.wip_schedule
        return obj

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        tz = pytz.timezone(self.request.event.timezone)
        if 'data' in ctx:
            for date in ctx['data']:
                if date.get('first_start') and date.get('last_end'):
                    start = date.get('first_start').astimezone(tz).replace(second=0, minute=0)
                    end = date.get('last_end').astimezone(tz)
                    date['height'] = int((end - start).seconds / 60 * 2)
                    date['hours'] = []
                    d = start
                    while d < end:
                        date['hours'].append(d.strftime('%H:%M'))
                        d += timedelta(hours=1)
                    for room in date['rooms']:
                        for talk in room.get('talks', []):
                            talk.top = int((talk.start.astimezone(tz) - start).seconds / 60 * 2)
                            talk.height = int(talk.duration * 2)
        return ctx


class FrabXmlView(ScheduleDataView):
    template_name = 'agenda/schedule.xml'


class FrabXCalView(ScheduleDataView):
    template_name = 'agenda/schedule.xcal'

    def get_context_data(self, event):
        ctx = super().get_context_data(event)
        ctx['domain'] = urlparse(settings.SITE_URL).netloc
        ctx['url'] = settings.SITE_URL
        return ctx


class ICalView(ScheduleDataView):
    def get(self, request, event, **kwargs):
        tz = pytz.timezone(self.request.event.timezone)
        schedule = self.get_object()
        netloc = urlparse(settings.SITE_URL).netloc

        cal = vobject.iCalendar()
        cal.add('prodid').value = '-//pretalx//{}//'.format(netloc)
        creation_time = datetime.now(pytz.utc)

        talks = schedule.talks.filter(
            is_visible=True
        ).prefetch_related('submission__speakers').select_related('submission', 'room').order_by('start')
        for talk in talks:
            vevent = cal.add('vevent')

            speakers = ', '.join([p.name for p in talk.submission.speakers.all()])
            vevent.add('summary').value = f'{talk.submission.title} - {speakers}'
            vevent.add('dtstamp').value = creation_time
            vevent.add('location').value = str(talk.room.name)
            vevent.add('uid').value = 'pretalx-{}-{}@{}'.format(
                request.event.slug, talk.submission.code,
                netloc
            )

            vevent.add('dtstart').value = talk.start.astimezone(tz)
            vevent.add('dtend').value = talk.end.astimezone(tz)
            vevent.add('description').value = talk.submission.abstract or ""
            # URL

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = f'attachment; filename="{request.event.slug}.ics"'
        return resp


class FrabJsonView(ScheduleDataView):

    def get(self, request, event, **kwargs):
        ctx = self.get_context_data(event)
        data = ctx['data']
        tz = pytz.timezone(self.request.event.timezone)
        schedule = self.get_object()
        result = {
            'version': schedule.version,
            'conference': {
                'acronym': request.event.slug,
                'title': str(request.event.name),
                'start': request.event.date_from.strftime('%Y-%m-%d'),
                'end': request.event.date_to.strftime('%Y-%m-%d'),
                'daysCount': request.event.duration,
                'timeslot_duration': '00:05',
                'days': [
                    {
                        'index': day['index'],
                        'date': day['start'].strftime('%Y-%m-%d'),
                        'day_start': day['start'].astimezone(tz).isoformat(),
                        'day_end': day['end'].astimezone(tz).isoformat(),
                        'rooms': {
                            str(room['name']): [
                                {
                                    'id': talk.submission.id,
                                    'guid': talk.submission.uuid,
                                    'logo': None,
                                    'date': talk.start.astimezone(tz).isoformat(),
                                    'start': talk.start.astimezone(tz).strftime('%H:%M'),
                                    'duration': talk.export_duration,
                                    'room': str(room['name']),
                                    'slug': talk.submission.code,
                                    'title': talk.submission.title,
                                    'subtitle': '',
                                    'track': None,
                                    'type': str(talk.submission.submission_type.name),
                                    'language': talk.submission.content_locale,
                                    'abstract': talk.submission.abstract,
                                    'description': talk.submission.description,
                                    'recording_license': '',
                                    'do_not_record': talk.submission.do_not_record,
                                    'persons': [
                                        {'id': person.id, 'name': person.get_display_name()}
                                        for person in talk.submission.speakers.all()
                                    ],
                                    'links': [],
                                    'attachments': [],
                                } for talk in room['talks']
                            ] for room in day['rooms']
                        }

                    } for day in data
                ]
            }
        }
        return JsonResponse({'schedule': result})


class TalkView(EventPageMixin, DetailView):
    context_object_name = 'talk'
    model = Submission
    slug_field = 'code'
    template_name = 'agenda/talk.html'

    def get_queryset(self):
        return Submission.objects.filter(event=self.request.event, state=SubmissionStates.CONFIRMED)

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        event_talks = self.request.event.current_schedule.talks.exclude(submission=self.object)
        ctx['speakers'] = []
        for speaker in self.object.speakers.all():  # TODO: there's bound to be an elegant annotation for this
            speaker.talk_profile = speaker.profiles.filter(event=self.request.event).first()
            speaker.other_talks = event_talks.filter(submission__speakers__in=[speaker])
            ctx['speakers'].append(speaker)
        return ctx


class ChangelogView(TemplateView):
    template_name = 'agenda/changelog.html'
