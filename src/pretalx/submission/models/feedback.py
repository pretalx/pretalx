# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy as _n
from django_scopes import ScopedManager

from pretalx.common.models.fields import MarkdownField
from pretalx.common.models.mixins import PretalxModel


class Feedback(PretalxModel):
    """The Feedback model allows for anonymous feedback by attendees to one or
    all speakers of a.

    :class:`~pretalx.submission.models.submission.Submission`.

    :param speaker: If the ``speaker`` attribute is not set, the feedback is
        assumed to be directed to all speakers.
    """

    talk = models.ForeignKey(
        to="submission.Submission",
        related_name="feedback",
        on_delete=models.PROTECT,
        verbose_name=_n("Session", "Sessions", 1),
    )
    speaker = models.ForeignKey(
        to="person.User",
        related_name="feedback",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_n("Speaker", "Speakers", 1),
    )
    rating = models.IntegerField(null=True, blank=True, verbose_name=_("Rating"))
    review = MarkdownField(verbose_name=_("Feedback"))

    objects = ScopedManager(event="talk__event")

    def __str__(self):
        """Help when debugging."""
        return f"Feedback(event={self.talk.event.slug}, talk={self.talk.title}, rating={self.rating})"
