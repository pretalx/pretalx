# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict
from urllib.parse import quote

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from i18nfield.fields import I18nTextField

from pretalx.agenda.rules import can_view_schedule, is_agenda_visible, is_widget_visible
from pretalx.common.models.mixins import PretalxModel
from pretalx.common.text.phrases import phrases
from pretalx.common.urls import EventUrls
from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.rules import is_reviewer
from pretalx.schedule.services import (
    freeze_schedule,
    get_cached_schedule_changes,
    unfreeze_schedule,
)
from pretalx.submission.rules import is_wip, orga_can_change_submissions


class Schedule(PretalxModel):
    """The Schedule model contains all scheduled.

    :class:`~pretalx.schedule.models.slot.TalkSlot` objects (visible or not)
    for a schedule release for an :class:`~pretalx.event.models.event.Event`.

    :param published: ``None`` if the schedule has not been published yet.
    """

    event = models.ForeignKey(
        to="event.Event", on_delete=models.PROTECT, related_name="schedules"
    )
    version = models.CharField(
        max_length=190,
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("Version of the conference schedule", "Version"),
    )
    published = models.DateTimeField(null=True, blank=True)
    comment = I18nTextField(
        null=True,
        blank=True,
        help_text=_("This text will be shown in the public changelog and the RSS feed.")
        + " "
        + phrases.base.use_markdown,
    )

    class Meta:
        ordering = ("-published",)
        unique_together = (("event", "version"),)
        rules_permissions = {
            "list": can_view_schedule,
            "view_widget": is_widget_visible | orga_can_change_submissions,
            "view": (~is_wip & is_agenda_visible)
            | orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "orga_view": orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "release": orga_can_change_submissions,
        }

    class urls(EventUrls):
        public = "{self.event.urls.schedule}v/{self.url_version}/"
        widget_data = "{public}widgets/schedule.json"
        nojs = "{public}nojs"

    def freeze(
        self, name: str, user=None, notify_speakers: bool = True, comment: str = None
    ):
        """Releases the current WIP schedule as a fixed schedule version.

        :param name: The new schedule name. May not be in use in this event,
            and cannot be 'wip' or 'latest'.
        :param user: The :class:`~pretalx.person.models.user.User` initiating
            the freeze.
        :param notify_speakers: Should notification emails for speakers with
            changed slots be generated?
        :param comment: Public comment for the release
        :rtype: Schedule
        """
        return freeze_schedule(self, name, user, notify_speakers, comment)

    freeze.alters_data = True

    def unfreeze(self, user=None):
        return unfreeze_schedule(self, user)

    unfreeze.alters_data = True

    @cached_property
    def scheduled_talks(self):
        """Returns all :class:`~pretalx.schedule.models.slot.TalkSlot` objects
        that have been scheduled and are visible in the schedule (that is, have
        been confirmed at the time of release)."""
        from pretalx.submission.models import SubmissionStates

        return (
            self.talks.select_related(
                "submission",
                "submission__event",
                "room",
            )
            .prefetch_related("submission__speakers")
            .filter(
                room__isnull=False,
                start__isnull=False,
                is_visible=True,
                submission__isnull=False,
            )
            .exclude(submission__state=SubmissionStates.DELETED)
        )

    @cached_property
    def breaks(self):
        return self.talks.select_related("room").filter(submission__isnull=True)

    @cached_property
    def slots(self):
        """Returns all.

        :class:`~pretalx.submission.models.submission.Submission` objects with
        :class:`~pretalx.schedule.models.slot.TalkSlot` objects in this
        schedule.
        """
        from pretalx.submission.models import Submission

        return Submission.objects.filter(
            id__in=self.scheduled_talks.values_list("submission", flat=True)
        )

    @cached_property
    def previous_schedule(self):
        """Returns the schedule released before this one, if any."""
        queryset = self.event.schedules.exclude(pk=self.pk)
        if self.published:
            queryset = queryset.filter(published__lt=self.published)
        return queryset.order_by("-published").first()

    def _handle_submission_move(self, submission, old_slots, new_slots):
        new = []
        canceled = []
        moved = []
        all_old_slots = [
            slot for slot in old_slots.values() if slot.submission_id == submission.pk
        ]
        all_new_slots = [
            slot for slot in new_slots.values() if slot.submission_id == submission.pk
        ]
        old_slots = [
            slot
            for slot in all_old_slots
            if not any(slot.is_same_slot(other_slot) for other_slot in all_new_slots)
        ]
        new_slots = [
            slot
            for slot in all_new_slots
            if not any(slot.is_same_slot(other_slot) for other_slot in all_old_slots)
        ]
        diff = len(old_slots) - len(new_slots)
        if diff > 0:
            canceled = old_slots[:diff]
            old_slots = old_slots[diff:]
        elif diff < 0:
            diff = -diff
            new = new_slots[:diff]
            new_slots = new_slots[diff:]
        for move in zip(old_slots, new_slots):
            old_slot = move[0]
            new_slot = move[1]
            moved.append(
                {
                    "submission": new_slot.submission,
                    "old_start": old_slot.local_start,
                    "new_start": new_slot.local_start,
                    "old_room": old_slot.room,
                    "new_room": new_slot.room,
                    "new_info": str(new_slot.room.speaker_info),
                    "new_slot": new_slot,
                }
            )
        return new, canceled, moved

    @cached_property
    def changes(self) -> dict:
        """Returns a dictionary of changes when compared to the previous
        version.

        The ``action`` field is either ``create`` or ``update``. If it's
        an update, the ``count`` integer, and the ``new_talks``,
        ``canceled_talks`` and ``moved_talks`` lists are also present.

        This property uses caching with different TTLs:
        - WIP schedules: 60 seconds
        - Released schedules: 10 minutes
        """
        return get_cached_schedule_changes(self)

    @cached_property
    def use_room_availabilities(self):
        from pretalx.schedule.models import Availability

        return Availability.objects.filter(
            room__isnull=False, event=self.event
        ).exists()

    def get_talk_warnings(
        self,
        talk,
        with_speakers=True,
        room_avails=None,
        speaker_avails=None,
        speaker_profiles=None,
    ) -> list:
        """A list of warnings that apply to this slot.

        Warnings are dictionaries with a ``type`` (``room`` or
        ``speaker``, for now) and a ``message`` fit for public display.
        This property only shows availability based warnings.
        """
        from pretalx.schedule.models import Availability, TalkSlot

        if not talk.start or not talk.submission or not talk.room:
            return []
        warnings = []
        availability = talk.as_availability
        url = talk.submission.orga_urls.base
        if self.use_room_availabilities:
            if room_avails is None:
                room_avails = talk.room.availabilities.all()
            if room_avails and not any(
                room_availability.contains(availability)
                for room_availability in Availability.union(room_avails)
            ):
                warnings.append(
                    {
                        "type": "room",
                        "message": str(
                            _(
                                "Room {room_name} is not available at the scheduled time."
                            )
                        ).format(
                            room_name=f"{phrases.base.quotation_open}{talk.room.name}{phrases.base.quotation_close}"
                        ),
                        "url": url,
                    }
                )
        overlaps = (
            TalkSlot.objects.filter(schedule=self, room=talk.room)
            .filter(
                models.Q(start__lt=talk.start, end__gt=talk.start)
                | models.Q(start__lt=talk.real_end, end__gt=talk.real_end)
                | models.Q(start__gt=talk.start, end__lt=talk.real_end)
                | models.Q(start=talk.start, end=talk.real_end)
            )
            .exclude(pk=talk.pk)
            .exists()
        )
        if overlaps:
            warnings.append(
                {
                    "type": "room_overlap",
                    "message": _(
                        "Another session in the same room overlaps with this one."
                    ),
                    "url": url,
                }
            )

        for speaker in talk.submission.speakers.all():
            if with_speakers:
                if speaker_profiles:
                    profile = speaker_profiles.get(speaker)
                else:
                    profile = speaker.event_profile(self.event)
                if profile and speaker_avails is not None:
                    profile_availabilities = speaker_avails.get(profile.pk)
                else:
                    profile_availabilities = (
                        list(profile.availabilities.all()) if profile else []
                    )
                if profile_availabilities and not any(
                    speaker_availability.contains(availability)
                    for speaker_availability in Availability.union(
                        profile_availabilities
                    )
                ):
                    warnings.append(
                        {
                            "type": "speaker",
                            "speaker": {
                                "name": speaker.get_display_name(),
                                "code": speaker.code,
                            },
                            "message": str(
                                _("{speaker} is not available at the scheduled time.")
                            ).format(speaker=speaker.get_display_name()),
                            "url": url,
                        }
                    )
            overlaps = (
                TalkSlot.objects.filter(
                    schedule=self, submission__speakers__in=[speaker]
                )
                .exclude(pk=talk.pk)
                .filter(
                    models.Q(start__lt=talk.start, end__gt=talk.start)
                    | models.Q(start__lt=talk.real_end, end__gt=talk.real_end)
                    | models.Q(start__gt=talk.start, end__lt=talk.real_end)
                    | models.Q(start=talk.start, end=talk.real_end)
                )
                .exists()
            )
            if overlaps:
                warnings.append(
                    {
                        "type": "speaker",
                        "speaker": {
                            "name": speaker.get_display_name(),
                            "code": speaker.code,
                        },
                        "message": str(
                            _(
                                "{speaker} is scheduled for another session at the same time."
                            )
                        ).format(speaker=speaker.get_display_name()),
                        "url": url,
                    }
                )

        return warnings

    def get_all_talk_warnings(self, ids=None, filter_updated=None):
        talks = (
            self.talks.filter(
                submission__isnull=False, start__isnull=False, room__isnull=False
            )
            .select_related(
                "submission",
                "room",
                "submission__event",
                "schedule__event",
            )
            .prefetch_related("submission__speakers")
        )
        if filter_updated:
            talks = talks.filter(updated__gte=filter_updated)
        with_speakers = self.event.cfp.request_availabilities
        room_avails = defaultdict(
            list,
            {
                room.pk: room.availabilities.all()
                for room in self.event.rooms.all().prefetch_related("availabilities")
            },
        )
        speaker_avails = None
        speaker_profiles = None
        if with_speakers:
            from pretalx.person.models import SpeakerProfile

            speaker_profiles = {
                profile.user: profile
                for profile in SpeakerProfile.objects.filter(
                    event=self.event
                ).select_related("user")
            }
            speaker_avails = defaultdict(
                list,
                {
                    profile.pk: profile.availabilities.all()
                    for profile in SpeakerProfile.objects.filter(
                        event=self.event
                    ).prefetch_related("availabilities")
                },
            )
        result = {}
        for talk in talks:
            talk_warnings = self.get_talk_warnings(
                talk=talk,
                with_speakers=with_speakers,
                room_avails=room_avails.get(talk.room_id) if talk.room_id else None,
                speaker_avails=speaker_avails,
                speaker_profiles=speaker_profiles,
            )
            if talk_warnings:
                result[talk] = talk_warnings
        return result

    @cached_property
    def warnings(self) -> dict:
        """A dictionary of warnings to be acknowledged before a release.

        ``talk_warnings`` contains a list of talk-related warnings.
        ``unscheduled`` is the list of talks without a scheduled slot,
        ``unconfirmed`` is the list of submissions that will not be
        visible due to their unconfirmed status, and ``no_track`` are
        submissions without a track in a conference that uses tracks.
        """
        from pretalx.submission.models import SubmissionStates

        talks = self.talks.filter(submission__isnull=False)
        warnings = {
            "talk_warnings": [
                {"talk": key, "warnings": value}
                for key, value in self.get_all_talk_warnings().items()
            ],
            "unscheduled": talks.filter(start__isnull=True).count(),
            "unconfirmed": talks.exclude(
                submission__state=SubmissionStates.CONFIRMED
            ).count(),
            "no_track": [],
        }
        if self.event.get_feature_flag("use_tracks"):
            warnings["no_track"] = talks.filter(submission__track_id__isnull=True)
        return warnings

    @cached_property
    def speakers_concerned(self):
        """Returns a dictionary of speakers with their new and changed talks in
        this schedule.

        Each speaker is assigned a dictionary with ``create`` and
        ``update`` fields, each containing a list of submissions.
        """
        result = {}
        if self.changes["action"] == "create":
            from pretalx.person.models import User

            for speaker in User.objects.filter(submissions__slots__schedule=self):
                talks = self.talks.filter(
                    submission__speakers=speaker,
                    room__isnull=False,
                    start__isnull=False,
                )
                if talks:
                    result[speaker] = {"create": talks, "update": []}
            return result

        if self.changes["count"] == len(self.changes["canceled_talks"]):
            return result

        speakers = defaultdict(lambda: {"create": [], "update": []})
        for new_talk in self.changes["new_talks"]:
            for speaker in new_talk.submission.speakers.all():
                speakers[speaker]["create"].append(new_talk)
        for moved_talk in self.changes["moved_talks"]:
            for speaker in moved_talk["submission"].speakers.all():
                speakers[speaker]["update"].append(moved_talk)
        return speakers

    def generate_notifications(self, save=False):
        """A list of unsaved :class:`~pretalx.mail.models.QueuedMail` objects
        to be sent on schedule release."""
        from pretalx.mail.models import MailTemplateRoles

        mails = []
        for speaker, data in self.speakers_concerned.items():
            locale = speaker.get_locale_for_event(self.event)
            slots = list(data.get("create") or []) + [
                talk["new_slot"] for talk in (data.get("update") or [])
            ]
            submissions = [slot.submission for slot in slots if slot]
            mails.append(
                self.event.get_mail_template(MailTemplateRoles.NEW_SCHEDULE).to_mail(
                    user=speaker,
                    event=self.event,
                    context_kwargs={"user": speaker},
                    commit=save,
                    locale=locale,
                    submissions=submissions,
                    attachments=[
                        {
                            "name": f"{slot.frab_slug}.ics",
                            "content": slot.full_ical().serialize(),
                            "content_type": "text/calendar",
                        }
                        for slot in slots
                    ],
                )
            )
        return mails

    generate_notifications.alters_data = True

    @cached_property
    def version_with_fallback(self):
        return self.version or "wip"

    @cached_property
    def url_version(self):
        return quote(self.version_with_fallback)

    @cached_property
    def is_archived(self):
        if not self.version:
            return False

        return self != self.event.current_schedule

    def build_data(self, all_talks=False, filter_updated=None, all_rooms=False):
        talks = self.talks.all()
        if not all_talks:
            talks = self.talks.filter(is_visible=True)
        if filter_updated:
            talks = talks.filter(updated__gte=filter_updated)
        talks = talks.select_related(
            "submission",
            "room",
            "submission__track",
            "submission__event",
            "submission__submission_type",
        ).prefetch_related("submission__speakers")
        talks = talks.order_by("start")
        rooms = set() if not all_rooms else set(self.event.rooms.all())
        tracks = set()
        speakers = set()
        result = {
            "talks": [],
            "version": self.version,
            "schedule_id": self.pk,
            "timezone": self.event.timezone,
            "event_start": self.event.date_from.isoformat(),
            "event_end": self.event.date_to.isoformat(),
        }
        show_do_not_record = self.event.cfp.request_do_not_record
        for talk in talks:
            rooms.add(talk.room)
            if talk.submission:
                tracks.add(talk.submission.track)
                speakers |= set(talk.submission.speakers.all())
                result["talks"].append(
                    {
                        "code": talk.submission.code if talk.submission else None,
                        "id": talk.id,
                        "title": (
                            talk.submission.title
                            if talk.submission
                            else talk.description
                        ),
                        "abstract": (
                            talk.submission.abstract if talk.submission else None
                        ),
                        "speakers": (
                            [speaker.code for speaker in talk.submission.speakers.all()]
                            if talk.submission
                            else None
                        ),
                        "track": talk.submission.track_id if talk.submission else None,
                        "start": talk.local_start,
                        "end": talk.local_end,
                        "room": talk.room_id,
                        "duration": talk.submission.get_duration(),
                        "updated": talk.updated.isoformat(),
                        "state": talk.submission.state if all_talks else None,
                        "content_locale": talk.submission.content_locale,
                        "do_not_record": (
                            talk.submission.do_not_record
                            if show_do_not_record
                            else None
                        ),
                    }
                )
            else:
                result["talks"].append(
                    {
                        "id": talk.id,
                        "title": talk.description,
                        "start": talk.start,
                        "end": talk.local_end,
                        "room": talk.room_id,
                    }
                )
        tracks.discard(None)
        tracks = sorted(tracks, key=lambda track: track.position or 0)
        result["tracks"] = [
            {
                "id": track.id,
                "name": track.name,
                "description": track.description,
                "color": track.color,
            }
            for track in tracks
        ]
        result["rooms"] = [
            {
                "id": room.id,
                "name": room.name,
                "description": room.description,
            }
            for room in self.event.rooms.all()
            if room in rooms
        ]
        include_avatar = self.event.cfp.request_avatar
        result["speakers"] = [
            {
                "code": user.code,
                "name": user.name,
                "avatar": (
                    user.get_avatar_url(event=self.event) if include_avatar else None
                ),
                "avatar_thumbnail_default": (
                    user.get_avatar_url(event=self.event, thumbnail="default")
                    if include_avatar
                    else None
                ),
                "avatar_thumbnail_tiny": (
                    user.get_avatar_url(event=self.event, thumbnail="tiny")
                    if include_avatar
                    else None
                ),
            }
            for user in speakers
        ]
        return result

    def __str__(self) -> str:
        """Help when debugging."""
        return f"Schedule(event={self.event.slug}, version={self.version})"
