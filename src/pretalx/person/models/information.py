from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretalx.common.mixins import LogMixin
from pretalx.common.phrases import phrases
from pretalx.common.urls import EventUrls


class SpeakerInformation(LogMixin, models.Model):
    """Represents any information organisers want to show all or some submitters or speakers."""
    event = models.ForeignKey(
        to='event.Event', related_name='information', on_delete=models.CASCADE
    )
    include_submitters = models.BooleanField(
        verbose_name=_('Include all submitters'),
        help_text=_('Show to every submitter regardless of their submissions\' status'),
        default=False,
    )
    exclude_unconfirmed = models.BooleanField(
        verbose_name=_('Exclude unconfirmed speakers'),
        help_text=_('Show to speakers only once they have confirmed attendance'),
        default=False,
    )
    title = I18nCharField(verbose_name=_('Subject'), max_length=200)
    text = I18nTextField(verbose_name=_('Text'), help_text=phrases.base.use_markdown)
    resource = models.FileField(
        verbose_name=_('file'),
        null=True,
        blank=True,
        help_text=_('Please try to keep your upload small, preferably below 16 MB.'),
    )

    objects = ScopedManager(event='event')

    class orga_urls(EventUrls):
        base = edit = '{self.event.orga_urls.information}{self.pk}/'
        delete = '{base}delete'
