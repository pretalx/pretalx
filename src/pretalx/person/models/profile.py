# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import uuid

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.agenda.rules import can_view_schedule, is_speaker_viewable
from pretalx.common.models.fields import MarkdownField
from pretalx.common.models.mixins import GenerateCode, PretalxModel
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.text.phrases import phrases
from pretalx.common.urls import EventUrls
from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.models.picture import ProfilePictureMixin
from pretalx.person.rules import (
    can_mark_speakers_arrived,
    is_administrator,
    is_reviewer,
)
from pretalx.schedule.models import Availability
from pretalx.submission.rules import orga_can_change_submissions


class SpeakerProfile(ProfilePictureMixin, GenerateCode, PretalxModel):
    """All :class:`~pretalx.event.models.event.Event` related data concerning
    a.

    :class:`~pretalx.person.models.user.User` is stored here.

    :param has_arrived: Can be set to track speaker arrival. Will be used in
        warnings about missing speakers.
    """

    code_scope = ("event",)

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
    biography = MarkdownField(verbose_name=_("Biography"), null=True, blank=True)
    has_arrived = models.BooleanField(
        default=False, verbose_name=_("The speaker has arrived")
    )
    internal_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name=phrases.base.internal_notes,
        help_text=phrases.base.internal_notes_help,
    )
    profile_picture = models.ForeignKey(
        "person.ProfilePicture",
        verbose_name=_("Profile picture"),
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
        invitation = "{self.event.urls.base}invite/{self.user.pw_reset_token}"

    class orga_urls(EventUrls):
        base = "{self.event.orga_urls.speakers}{self.code}/"
        password_reset = "{base}reset"  # noqa: S105  -- URL pattern, not a password
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
    def guid(self) -> str | None:
        prefix = None
        code = None
        if self.user_id:
            prefix = "user"
            code = self.user.code
        if not code:
            prefix = "speaker"
            code = self.code
        if not code:
            # code is always set except for unsaved objects
            return None
        return str(
            uuid.uuid5(GlobalSettings().get_instance_identifier(), f"{prefix}:{code}")
        )

    @cached_property
    def talks(self):
        """A queryset of.

        :class:`~pretalx.submission.models.submission.Submission` objects.

        Contains all visible talks by this user on this event.
        """
        return self.event.talks.filter(speakers=self)

    @cached_property
    def current_talk_slots(self):
        from pretalx.person.domain.queries.profile import (  # noqa: PLC0415 -- thin method
            visible_talk_slots,
        )

        return visible_talk_slots(self)

    @cached_property
    def all_answers(self):
        """A queryset of :class:`~pretalx.submission.models.question.Answer`
        objects.

        Includes all answers the user has given either for themselves or
        for their talks for this event.
        """
        from pretalx.submission.domain.queries.question import (  # noqa: PLC0415 -- thin method
            answers_for_speaker,
        )

        return answers_for_speaker(self)

    @cached_property
    def reviewer_answers(self):
        return self.all_answers.filter(question__is_visible_to_reviewers=True)

    def get_instance_data(self):
        data = {}
        if not self._state.adding:
            data = {
                "name": self.name or (self.user.name if self.user else None),
                "email": self.user.email if self.user else None,
                "profile_picture": (
                    self.profile_picture.avatar.name
                    if self.profile_picture_id and self.profile_picture.avatar
                    else None
                ),
            }
        return super().get_instance_data() | data

    @cached_property
    def full_availability(self):
        return Availability.union(self.availabilities.all())
