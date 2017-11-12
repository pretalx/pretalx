from django.db import models
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField

from pretalx.common.mixins import LogMixin
from pretalx.common.urls import EventUrls


class Room(LogMixin, models.Model):
    event = models.ForeignKey(
        to='event.Event',
        on_delete=models.PROTECT,
        related_name='rooms',
    )
    name = I18nCharField(
        max_length=100,
        verbose_name=_('Name'),
    )
    description = I18nCharField(
        max_length=1000,
        null=True, blank=True,
        verbose_name=_('Description'),
        help_text=_('A description, for example directions.'),
    )
    capacity = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name=_('Capacity'),
        help_text=_('How many people can fit in the room?')
    )
    position = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name=_('Position'),
        help_text=_('This is the order that rooms are displayed in in the schedule (lower = left).'),
    )

    class Meta:
        ordering = ('position', )

    class urls(EventUrls):
        settings_base = '{self.event.orga_urls.room_settings}/{self.pk}'
        edit_settings = '{settings_base}/edit'
        delete = '{settings_base}/delete'

    def __str__(self) -> str:
        return str(self.name)
