from datetime import datetime

from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretalx.common.mixins import LogMixin
from pretalx.common.phrases import phrases
from pretalx.common.urls import EventUrls


class CfP(LogMixin, models.Model):
    """
    Every :class:`~pretalx.event.models.event.Event` has one Call for P(apers|articipation|roposals).

    :param deadline: The regular deadline. Please note that submissions can be available for longer than this if different deadlines are configured on single submission types.
    """
    event = models.OneToOneField(to='event.Event', on_delete=models.PROTECT)
    headline = I18nCharField(
        max_length=300, null=True, blank=True, verbose_name=_('headline')
    )
    text = I18nTextField(
        null=True,
        blank=True,
        verbose_name=_('text'),
        help_text=phrases.base.use_markdown,
    )
    default_type = models.ForeignKey(
        to='submission.SubmissionType',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('Default submission type'),
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('deadline'),
        help_text=_(
            'Please put in the last date you want to accept submissions from users.'
        ),
    )
    help_text_track = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the track selection field'),
    )
    help_text_abstract = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the abstract field'),
        default=_('A brief description of your talk. It should be a summary of a longer description if provided.'),
    )
    help_text_description = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the description field'),
        default=_('A long description of your talk.'),
    )
    help_text_notes = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the notes for the organiser field'),
        default=_('These notes are meant for the organiser and won\'t be made public.'),
    )
    help_text_slot_count = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the slot count field'),
        default=_('How many times this talk will be held.'),
    )
    help_text_image = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the talk image field'),
        default=_('Use this if you want an illustration to go with your submission. This content will be shown publicly.'),
    )
    help_text_additional_speaker = I18nTextField(
        null=True,
        blank=True,
        help_text=_('Help text for the additional speaker field of the CfP form'),
        default=_('If you have a co-speaker, please add their email address here, and we will invite them to create an account. If you have more than one co-speaker, you can add more speakers after finishing the submission process.'),
    )

    objects = ScopedManager(event='event')

    class urls(EventUrls):
        base = '{self.event.orga_urls.cfp}'
        questions = '{base}questions/'
        new_question = '{questions}new'
        remind_questions = '{questions}remind'
        text = edit_text = '{base}text'
        types = '{base}types/'
        new_type = '{types}new'
        tracks = '{base}tracks/'
        new_track = '{tracks}new'
        public = '{self.event.urls.base}cfp'
        submit = '{self.event.urls.base}submit/'

    def __str__(self) -> str:
        """Help with debugging."""
        return f'CfP(event={self.event.slug})'

    @cached_property
    def is_open(self) -> bool:
        """``True`` if ``max_deadline`` is not over yet, or if no deadline is set."""
        if self.deadline is None:
            return True
        return self.max_deadline >= now() if self.max_deadline else True

    @cached_property
    def max_deadline(self) -> datetime:
        """Returns the latest date any submission is possible.

        This includes the deadlines set on any submission type for this event."""
        deadlines = list(
            self.event.submission_types.filter(deadline__isnull=False).values_list(
                'deadline', flat=True
            )
        )
        if self.deadline:
            deadlines.append(self.deadline)
        return max(deadlines) if deadlines else None
