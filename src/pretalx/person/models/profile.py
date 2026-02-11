# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.agenda.rules import can_view_schedule, is_speaker_viewable
from pretalx.common.models.fields import MarkdownField
from pretalx.common.models.mixins import GenerateCode, PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.rules import (
    can_mark_speakers_arrived,
    is_administrator,
    is_reviewer,
)
from pretalx.submission.rules import orga_can_change_submissions


class SpeakerProfile(GenerateCode, PretalxModel):
    """All :class:`~pretalx.event.models.event.Event` related data concerning
    a.

    :class:`~pretalx.person.models.user.User` is stored here.

    :param has_arrived: Can be set to track speaker arrival. Will be used in
        warnings about missing speakers.
    """

    _code_scope = ("event",)

    user = models.ForeignKey(
        to="person.User",
        related_name="profiles",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    event = models.ForeignKey(
        to="event.Event", related_name="+", on_delete=models.CASCADE
    )
    name = models.CharField(
        max_length=120, null=True, blank=True, verbose_name=_("Name")
    )
    code = models.CharField(max_length=16)
    biography = MarkdownField(
        verbose_name=_("Biography"),
        null=True,
        blank=True,
    )
    has_arrived = models.BooleanField(
        default=False, verbose_name=_("The speaker has arrived")
    )
    internal_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Internal notes"),
        help_text=_(
            "Internal notes for other organisers/reviewers. Not visible to the speakers or the public."
        ),
    )
    profile_picture = models.ForeignKey(
        "person.ProfilePicture",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="speakers",
    )

    log_prefix = "pretalx.user.profile"

    class Meta:
        unique_together = (("event", "code"), ("event", "user"))
        # These permissions largely apply to event-scoped user actions
        rules_permissions = {
            "list": can_view_schedule | (is_reviewer & can_view_speaker_names),
            "reviewer_list": is_reviewer & can_view_speaker_names,
            "orga_list": orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "view": is_speaker_viewable
            | orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "orga_view": orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "create": is_administrator,
            "update": orga_can_change_submissions,
            "mark_arrived": orga_can_change_submissions & can_mark_speakers_arrived,
            "delete": is_administrator,
        }

    class urls(EventUrls):
        public = "{self.event.urls.base}speaker/{self.code}/"
        social_image = "{public}og-image"
        talks_ical = "{public}talks.ics"

    class orga_urls(EventUrls):
        base = "{self.event.orga_urls.speakers}{self.code}/"
        password_reset = "{base}reset"
        toggle_arrived = "{base}toggle-arrived"
        send_mail = "{self.event.orga_urls.compose_mails_sessions}?speakers={self.code}"

    def __str__(self):
        """Help when debugging."""
        return (
            f"SpeakerProfile(event={self.event.slug}, user={self.get_display_name()})"
        )

    def get_display_name(self):
        return (
            self.name
            or (self.user.name if self.user else None)
            or str(_("Unnamed speaker"))
        )

    @cached_property
    def talks(self):
        """A queryset of.

        :class:`~pretalx.submission.models.submission.Submission` objects.

        Contains all visible talks by this user on this event.
        """
        return self.event.talks.filter(speakers=self)

    def get_talk_slots(self, schedule=None):
        schedule = schedule or self.event.current_schedule
        from pretalx.schedule.models import TalkSlot  # noqa: PLC0415

        if not schedule:
            return TalkSlot.objects.none()
        return (
            schedule.talks.filter(submission__speakers=self, is_visible=True)
            .select_related(
                "submission",
                "room",
                "submission__event",
                "submission__track",
                "submission__submission_type",
            )
            .with_sorted_speakers()
        )

    @cached_property
    def current_talk_slots(self):
        return self.get_talk_slots()

    @cached_property
    def answers(self):
        """A queryset of :class:`~pretalx.submission.models.question.Answer`
        objects.

        Includes all answers the user has given either for themselves or
        for their talks for this event.
        """
        from pretalx.submission.models import Answer, Submission  # noqa: PLC0415

        submissions = Submission.objects.filter(event=self.event, speakers=self)
        return Answer.objects.filter(
            models.Q(submission__in=submissions) | models.Q(person=self.user)
        ).order_by("question__position")

    @property
    def reviewer_answers(self):
        return self.answers.filter(question__is_visible_to_reviewers=True).order_by(
            "question__position"
        )

    @cached_property
    def avatar(self):
        if self.profile_picture_id:
            return self.profile_picture.avatar

    @cached_property
    def avatar_url(self):
        if self.profile_picture_id:
            return self.profile_picture.get_avatar_url(event=self.event)

    def _get_instance_data(self):
        data = {}
        if self.pk:
            data = {
                "name": self.name or (self.user.name if self.user else None),
                "email": self.user.email if self.user else None,
                "avatar": (
                    self.profile_picture.avatar.name
                    if self.profile_picture_id and self.profile_picture.avatar
                    else None
                ),
            }
        return super()._get_instance_data() | data

    @cached_property
    def full_availability(self):
        from pretalx.schedule.models import Availability  # noqa: PLC0415

        return Availability.union(self.availabilities.all())
