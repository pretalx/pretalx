from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_scopes import ScopedManager

from pretalx.common.mixins import LogMixin


class Resource(LogMixin, models.Model):
    """Resources are file uploads belonging to a :class:`~pretalx.submission.models.submission.Submission`."""
    submission = models.ForeignKey(
        to='submission.Submission', related_name='resources', on_delete=models.PROTECT
    )
    resource = models.FileField(
        verbose_name=_('file'),
        help_text=_('Please try to keep your upload small, preferably below 16 MB.'),
    )
    description = models.CharField(
        null=True, blank=True, max_length=1000, verbose_name=_('description')
    )

    objects = ScopedManager(event='submission__event')

    def __str__(self):
        """Help when debugging."""
        return f'Resource(event={self.submission.event.slug}, submission={self.submission.title})'
