from collections import defaultdict, namedtuple
from contextlib import suppress
from urllib.parse import quote

import pytz
from django.conf import settings
from django.db import models, transaction
from django.template.loader import get_template
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.timezone import override as tzoverride
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django_scopes import ScopedManager
from i18nfield.fields import I18nTextField

from pretalx.agenda.tasks import export_schedule_html
from pretalx.common.mixins.models import LogMixin
from pretalx.common.phrases import phrases
from pretalx.common.urls import EventUrls
from pretalx.person.models import SpeakerProfile, User
from pretalx.schedule.signals import schedule_release
from pretalx.submission.models import SubmissionStates


class Schedule(LogMixin, models.Model):
    """The Schedule model contains all scheduled.

    :class:`~pretalx.schedule.models.slot.TalkSlot` objects (visible or not)
    for a schedule release for an :class:`~pretalx.event.models.event.Event`.

    :param published: ``None`` if the schedule has not been published yet.
    """

    event = models.ForeignKey(
        to="event.Event", on_delete=models.PROTECT, related_name="schedules"
    )
    version = models.CharField(
        max_length=190, null=True, blank=True, verbose_name=_("version")
    )
    published = models.DateTimeField(null=True, blank=True)
    comment = I18nTextField(
        null=True,
        blank=True,
        help_text=_("This text will be shown in the public changelog and the RSS feed.")
        + " "
        + phrases.base.use_markdown,
    )

    objects = ScopedManager(event="event")

    class Meta:
        ordering = ("-published",)
        unique_together = (("event", "version"),)

    class urls(EventUrls):
        public = "{self.event.urls.schedule}v/{self.url_version}/"
        widget_data = "{public}widget/v2.json"
        nojs = "{public}nojs"

    @transaction.atomic
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
        from pretalx.schedule.models import TalkSlot

        if name in ["wip", "latest"]:
            raise Exception(f'Cannot use reserved name "{name}" for schedule version.')
        if self.version:
            raise Exception(
                f'Cannot freeze schedule version: already versioned as "{self.version}".'
            )
        if not name:
            raise Exception("Cannot create schedule version without a version name.")

        self.version = name
        self.comment = comment
        self.published = now()
        self.save(update_fields=["published", "version", "comment"])
        self.log_action("pretalx.schedule.release", person=user, orga=True)

        wip_schedule = Schedule.objects.create(event=self.event)

        # Set visibility
        self.talks.all().update(is_visible=False)
        self.talks.filter(
            models.Q(submission__state=SubmissionStates.CONFIRMED)
            | models.Q(submission__isnull=True),
            start__isnull=False,
        ).update(is_visible=True)

        talks = []
        for talk in self.talks.select_related("submission", "room").all():
            talks.append(talk.copy_to_schedule(wip_schedule, save=False))
        TalkSlot.objects.bulk_create(talks)

        if notify_speakers:
            self.generate_notifications(save=True)

        with suppress(AttributeError):
            del wip_schedule.event.wip_schedule
        with suppress(AttributeError):
            del wip_schedule.event.current_schedule

        schedule_release.send_robust(self.event, schedule=self, user=user)

        if self.event.feature_flags["export_html_on_release"]:
            if settings.HAS_CELERY:
                export_schedule_html.apply_async(kwargs={"event_id": self.event.id})
            else:
                self.event.cache.set("rebuild_schedule_export", True, None)
        return self, wip_schedule

    freeze.alters_data = True

    @transaction.atomic
    def unfreeze(self, user=None):
        """Resets the current WIP schedule to an older schedule version."""
        from pretalx.schedule.models import TalkSlot

        if not self.version:
            raise Exception("Cannot unfreeze schedule version: not released yet.")

        # collect all talks, which have been added since this schedule (#72)
        submission_ids = self.talks.all().values_list("submission_id", flat=True)
        talks = self.event.wip_schedule.talks.exclude(
            submission_id__in=submission_ids
        ).union(self.talks.all())

        wip_schedule = Schedule.objects.create(event=self.event)
        new_talks = []
        for talk in talks:
            new_talks.append(talk.copy_to_schedule(wip_schedule, save=False))
        TalkSlot.objects.bulk_create(new_talks)

        self.event.wip_schedule.talks.all().delete()
        self.event.wip_schedule.delete()

        with suppress(AttributeError):
            del wip_schedule.event.wip_schedule

        return self, wip_schedule

    unfreeze.alters_data = True

    @cached_property
    def scheduled_talks(self):
        """Returns all :class:`~pretalx.schedule.models.slot.TalkSlot` objects
        that have been scheduled."""
        return (
            self.talks.select_related(
                "submission",
                "submission__event",
                "room",
            )
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
            slot for slot in old_slots if slot.submission_id == submission.pk
        ]
        all_new_slots = [
            slot for slot in new_slots if slot.submission_id == submission.pk
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
                    "old_start": old_slot.start.astimezone(self.tz),
                    "new_start": new_slot.start.astimezone(self.tz),
                    "old_room": old_slot.room.name,
                    "new_room": new_slot.room.name,
                    "new_info": new_slot.room.speaker_info,
                }
            )
        return new, canceled, moved

    @cached_property
    def tz(self):
        return pytz.timezone(self.event.timezone)

    @cached_property
    def changes(self) -> dict:
        """Returns a dictionary of changes when compared to the previous
        version.

        The ``action`` field is either ``create`` or ``update``. If it's
        an update, the ``count`` integer, and the ``new_talks``,
        ``canceled_talks`` and ``moved_talks`` lists are also present.
        """
        result = {
            "count": 0,
            "action": "update",
            "new_talks": [],
            "canceled_talks": [],
            "moved_talks": [],
        }
        if not self.previous_schedule:
            result["action"] = "create"
            return result

        old_slots = list(self.previous_schedule.scheduled_talks)
        new_slots = list(self.scheduled_talks)

        Slot = namedtuple("Slot", ["submission", "room", "start"])
        old_slot_set = set(
            Slot(slot.submission, slot.room, slot.start) for slot in old_slots
        )
        new_slot_set = set(
            Slot(slot.submission, slot.room, slot.start) for slot in new_slots
        )
        old_submissions = set(slot.submission for slot in old_slots)
        new_submissions = set(slot.submission for slot in new_slots)
        handled_submissions = set()
        new_by_submission = defaultdict(list)
        old_by_submission = defaultdict(list)
        for slot in new_slot_set:
            new_by_submission[slot.submission].append(slot)
        for slot in old_slot_set:
            old_by_submission[slot.submission].append(slot)

        moved_or_missing = old_slot_set - new_slot_set - {None}
        moved_or_new = new_slot_set - old_slot_set - {None}

        for entry in moved_or_missing:
            if entry.submission in handled_submissions or not entry.submission:
                continue
            if entry.submission not in new_submissions:
                result["canceled_talks"] += old_by_submission[entry.submission]
            else:
                new, canceled, moved = self._handle_submission_move(
                    entry.submission, old_slots, new_slots
                )
                result["new_talks"] += new
                result["canceled_talks"] += canceled
                result["moved_talks"] += moved
            handled_submissions.add(entry.submission)
        for entry in moved_or_new:
            if entry.submission in handled_submissions:
                continue
            if entry.submission not in old_submissions:
                result["new_talks"] += new_by_submission[entry.submission]
            else:
                new, canceled, moved = self._handle_submission_move(
                    entry.submission, old_slots, new_slots
                )
                result["new_talks"] += new
                result["canceled_talks"] += canceled
                result["moved_talks"] += moved
            handled_submissions.add(entry.submission)

        result["count"] = (
            len(result["new_talks"])
            + len(result["canceled_talks"])
            + len(result["moved_talks"])
        )
        return result

    @cached_property
    def use_room_availabilities(self):
        return any(
            room.availabilities.all()
            for room in self.event.rooms.all().prefetch_related("availabilities")
        )

    def get_talk_warnings(
        self,
        talk,
        with_speakers=True,
        room_avails=None,
        speaker_avails=None,
    ) -> list:
        """A list of warnings that apply to this slot.

        Warnings are dictionaries with a ``type`` (``room`` or
        ``speaker``, for now) and a ``message`` fit for public display.
        This property only shows availability based warnings.
        """
        from pretalx.schedule.models import Availability, TalkSlot

        if not talk.start or not talk.submission:
            return []
        warnings = []
        availability = talk.as_availability
        if talk.room and self.use_room_availabilities:
            if room_avails is None:
                room_avails = talk.room.availabilities.all()
            if not any(
                room_availability.contains(availability)
                for room_availability in Availability.union(room_avails)
            ):
                warnings.append(
                    {
                        "type": "room",
                        "message": _(
                            "The room is not available at the scheduled time."
                        ),
                    }
                )
        if talk.room:
            overlaps = (
                TalkSlot.objects.filter(schedule=self, room=talk.room)
                .filter(
                    models.Q(start__lt=talk.start, end__gt=talk.start)
                    | models.Q(start__lt=talk.real_end, end__gt=talk.real_end)
                    | models.Q(start__gt=talk.start, end__lt=talk.real_end)
                )
                .exclude(pk=talk.pk)
                .exists()
            )
            if overlaps:
                warnings.append(
                    {
                        "type": "room_overlap",
                        "message": _(
                            "There's an overlapping session scheduled in this room."
                        ),
                    }
                )

        for speaker in talk.submission.speakers.all():
            if with_speakers:
                profile = speaker.event_profile(event=self.event)
                if speaker_avails is not None:
                    profile_availabilities = speaker_avails.get(profile.pk)
                else:
                    profile_availabilities = list(profile.availabilities.all())
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
                                "id": speaker.pk,
                            },
                            "message": _(
                                "A speaker is not available at the scheduled time."
                            ),
                        }
                    )
            overlaps = (
                TalkSlot.objects.filter(
                    schedule=self, submission__speakers__in=[speaker]
                )
                .filter(
                    models.Q(start__lt=talk.start, end__gt=talk.start)
                    | models.Q(start__lt=talk.real_end, end__gt=talk.real_end)
                    | models.Q(start__gt=talk.start, end__lt=talk.real_end)
                )
                .exists()
            )
            if overlaps:
                warnings.append(
                    {
                        "type": "speaker",
                        "speaker": {
                            "name": speaker.get_display_name(),
                            "id": speaker.pk,
                        },
                        "message": _(
                            "A speaker is holding another session at the scheduled time."
                        ),
                    }
                )

        return warnings

    def get_all_talk_warnings(self, talks=None):
        talks = talks or self.talks.filter(submission__isnull=False).select_related(
            "submission", "room"
        ).prefetch_related("submission__speakers")
        result = {}
        with_speakers = self.event.cfp.request_availabilities
        room_avails = defaultdict(
            list,
            {
                room.pk: room.availabilities.all()
                for room in self.event.rooms.all().prefetch_related("availabilities")
            },
        )
        speaker_avails = None
        if with_speakers:
            speaker_avails = defaultdict(
                list,
                {
                    profile.pk: profile.availabilities.all()
                    for profile in SpeakerProfile.objects.filter(
                        event=self.event
                    ).prefetch_related("availabilities")
                },
            )
        for talk in talks:
            talk_warnings = self.get_talk_warnings(
                talk=talk,
                with_speakers=with_speakers,
                room_avails=room_avails.get(talk.room_id) if talk.room_id else None,
                speaker_avails=speaker_avails,
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
        talks = (
            self.talks.filter(submission__isnull=False)
            .select_related("submission", "room")
            .prefetch_related("submission__speakers")
        )
        warnings = {
            "talk_warnings": [
                {"talk": key, "warnings": value}
                for key, value in self.get_all_talk_warnings(
                    talks.filter(start__isnull=False)
                ).items()
            ],
            "unscheduled": talks.filter(start__isnull=True).count(),
            "unconfirmed": talks.exclude(
                submission__state=SubmissionStates.CONFIRMED
            ).count(),
            "no_track": [],
        }
        if self.event.feature_flags["use_tracks"]:
            warnings["no_track"] = talks.filter(
                submission__track_id__isnull=True
            ).count()
        return warnings

    @cached_property
    def speakers_concerned(self):
        """Returns a dictionary of speakers with their new and changed talks in
        this schedule.

        Each speaker is assigned a dictionary with ``create`` and
        ``update`` fields, each containing a list of submissions.
        """
        if self.changes["action"] == "create":
            result = {}
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
            return []

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
        mails = []
        for speaker in self.speakers_concerned:
            locale = (
                speaker.locale
                if speaker.locale in self.event.locales
                else self.event.locale
            )
            with override(locale), tzoverride(self.tz):
                notifications = get_template(
                    "schedule/speaker_notification.txt"
                ).render({"speaker": speaker, **self.speakers_concerned[speaker]})
            mails.append(
                self.event.update_template.to_mail(
                    user=speaker,
                    event=self.event,
                    context_kwargs={"user": speaker},
                    context={"notifications": notifications},
                    commit=save,
                    locale=locale,
                )
            )
        return mails

    generate_notifications.alters_data = True

    @cached_property
    def url_version(self):
        return quote(self.version) if self.version else "wip"

    @cached_property
    def is_archived(self):
        if not self.version:
            return False

        return self != self.event.current_schedule

    def __str__(self) -> str:
        """Help when debugging."""
        return f"Schedule(event={self.event.slug}, version={self.version})"
