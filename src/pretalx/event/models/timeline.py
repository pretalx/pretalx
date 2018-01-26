from django.db import models
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField, I18nTextField

from pretalx.common.mixins import LogMixin


class TimelineEvent(LogMixin, models.Model):
    event = models.ForeignKey(
        to='event.Event',
        on_delete=models.PROTECT,
        related_name='timeline_events',
    )
    datetime = models.DateTimeField(
        verbose_name=_('Event start date'),
    )
    title = I18nCharField(
        max_length=200,
        verbose_name=_('Title'),
    )
    description = I18nTextField(
        max_length=200,
        verbose_name=_('Description'),
        null=True, blank=True,
    )
    url = models.URLField(
        verbose_name=_('URL'),
        null=True, blank=True,
    )
    is_public = models.BooleanField(
        default=True,
        verbose_name=_('Event is public'),
    )

    class Meta:
        ordering = ('datetime', )
