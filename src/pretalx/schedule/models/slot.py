from datetime import datetime, timedelta
from urllib.parse import urlparse

import pytz
from django.db import models

from pretalx.common.mixins import LogMixin
from pretalx.common.urls import get_base_url


class TalkSlot(LogMixin, models.Model):
    submission = models.ForeignKey(
        to='submission.Submission',
        on_delete=models.PROTECT,
        related_name='slots',
    )
    room = models.ForeignKey(
        to='schedule.Room',
        on_delete=models.PROTECT,
        related_name='talks',
        null=True, blank=True,
    )
    schedule = models.ForeignKey(
        to='schedule.Schedule',
        on_delete=models.PROTECT,
        related_name='talks',
    )
    is_visible = models.BooleanField()
    start = models.DateTimeField(null=True)
    end = models.DateTimeField(null=True)

    class Meta:
        unique_together = (('submission', 'schedule'), )

    @property
    def event(self):
        return self.submission.event

    @property
    def duration(self):
        if self.start and self.end:
            return int((self.end - self.start).total_seconds() / 60)
        return self.submission.get_duration()

    @property
    def export_duration(self):
        duration = timedelta(minutes=self.duration)
        days = duration.days
        hours = duration.total_seconds() // 3600 - days * 24
        minutes = duration.seconds // 60 % 60
        fmt = f'{minutes:02}'
        if hours or days:
            fmt = f'{hours:02}:{fmt}'
            if days:
                fmt = f'{days}:{fmt}'
        else:
            fmt = f'00:{fmt}'
        return fmt

    @property
    def pentabarf_export_duration(self):
        duration = timedelta(minutes=self.duration)
        days = duration.days
        hours = duration.total_seconds() // 3600 - days * 24
        minutes = duration.seconds // 60 % 60
        return f'{hours:02}{minutes:02}00'

    def copy_to_schedule(self, new_schedule, save=True):
        new_slot = TalkSlot(schedule=new_schedule)

        for field in [f for f in self._meta.fields if f.name not in ('id', 'schedule')]:
            setattr(new_slot, field.name, getattr(self, field.name))

        if save:
            new_slot.save()
        return new_slot

    def build_ical(self, calendar, creation_time=None, netloc=None):
        creation_time = creation_time or datetime.now(pytz.utc)
        netloc = netloc or urlparse(get_base_url(self.event)).netloc
        tz = pytz.timezone(self.submission.event.timezone)

        vevent = calendar.add('vevent')
        vevent.add('summary').value = f'{self.submission.title} - {self.submission.display_speaker_names}'
        vevent.add('dtstamp').value = creation_time
        vevent.add('location').value = str(self.room.name)
        vevent.add('uid').value = 'pretalx-{}-{}@{}'.format(
            self.submission.event.slug, self.submission.code,
            netloc
        )

        vevent.add('dtstart').value = self.start.astimezone(tz)
        vevent.add('dtend').value = self.end.astimezone(tz)
        vevent.add('description').value = self.submission.abstract or ""
        vevent.add('url').value = self.submission.urls.public.full()
