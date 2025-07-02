import json
from collections import defaultdict, namedtuple
from contextlib import suppress
from urllib.parse import quote

from django.conf import settings
from django.db import models, transaction
from django.db.utils import DatabaseError
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from i18nfield.fields import I18nTextField

from pretalx.agenda.rules import can_view_schedule, is_agenda_visible, is_widget_visible
from pretalx.agenda.tasks import export_schedule_html
from pretalx.common.models.mixins import PretalxModel
from pretalx.common.text.phrases import phrases
from pretalx.common.urls import EventUrls
from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.rules import is_reviewer
from pretalx.schedule.notifications import render_notifications
from pretalx.schedule.signals import schedule_release
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
        from pretalx.submission.models import SubmissionStates

        if name in ("wip", "latest"):
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

        # Create WIP schedule first, to avoid race conditions
        wip_schedule = Schedule.objects.create(event=self.event)

        self.save(update_fields=["published", "version", "comment"])
        self.log_action("pretalx.schedule.release", person=user, orga=True)

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

        if self.event.get_feature_flag("export_html_on_release"):
            if not settings.CELERY_TASK_ALWAYS_EAGER:
                export_schedule_html.apply_async(
                    kwargs={"event_id": self.event.id}, ignore_result=True
                )
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
        talks = self.event.wip_schedule.talks.exclude(submission_id__in=submission_ids)
        try:
            talks = list(
                talks.union(self.talks.all())
            )  # We force evaluation to catch the DatabaseError early
        except DatabaseError:  # SQLite cannot deal with ordered querysets in union()
            talks = set(talks) | set(self.talks.all())

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

    def _serialize_changes(self, changes: dict) -> dict:
        """Serialize changes data for caching by replacing submission/slot objects with IDs/codes."""
        serialized = {
            "count": changes["count"],
            "action": changes["action"],
            "new_talks": [],
            "canceled_talks": [],
            "moved_talks": [],
        }

        for talk in changes["new_talks"]:
            serialized["new_talks"].append(
                {
                    "id": talk.id,
                    "submission_code": (
                        talk.submission.code if talk.submission else None
                    ),
                }
            )

        for talk in changes["canceled_talks"]:
            serialized["canceled_talks"].append(
                {
                    "id": talk.id,
                    "submission_code": (
                        talk.submission.code if talk.submission else None
                    ),
                }
            )

        for moved in changes["moved_talks"]:
            serialized["moved_talks"].append(
                {
                    "submission_code": (
                        moved["submission"].code if moved["submission"] else None
                    ),
                    "old_start": (
                        moved["old_start"].isoformat() if moved["old_start"] else None
                    ),
                    "new_start": (
                        moved["new_start"].isoformat() if moved["new_start"] else None
                    ),
                    "old_room": moved["old_room"].pk if moved["old_room"] else None,
                    "new_room": moved["new_room"].pk if moved["new_room"] else None,
                    "new_info": moved["new_info"],
                    "new_slot_id": moved["new_slot"].id if moved["new_slot"] else None,
                }
            )

        return serialized

    def _deserialize_changes(self, serialized: dict) -> dict:
        """Deserialize cached changes data by replacing IDs/codes with actual objects."""
        submission_codes = set()
        slot_ids = set()
        room_ids = set()

        for item in serialized["new_talks"] + serialized["canceled_talks"]:
            if item["submission_code"]:
                submission_codes.add(item["submission_code"])
            slot_ids.add(item["id"])

        for item in serialized["moved_talks"]:
            if item["submission_code"]:
                submission_codes.add(item["submission_code"])
            if item["new_slot_id"]:
                slot_ids.add(item["new_slot_id"])
            if item.get("new_room_id"):
                room_ids.add(item["new_room_id"])

        from pretalx.schedule.models import Room, TalkSlot
        from pretalx.submission.models import Submission

        submissions_by_code = {}
        if submission_codes:
            submissions_by_code = {
                sub.code: sub
                for sub in Submission.objects.filter(
                    code__in=submission_codes, event=self.event
                )
                .select_related("event")
                .prefetch_related("speakers")
            }

        slots_by_id = {}
        if slot_ids:
            slots_by_id = {
                slot.id: slot
                for slot in TalkSlot.objects.filter(id__in=slot_ids).select_related(
                    "submission", "room", "schedule"
                )
            }

        rooms_by_id = {}
        if room_ids:
            rooms_by_id = {
                room.id: room
                for room in Room.objects.filter(id__in=room_ids, event=self.event)
            }

        changes = {
            "count": serialized["count"],
            "action": serialized["action"],
            "new_talks": [],
            "canceled_talks": [],
            "moved_talks": [],
        }

        for item in serialized["new_talks"]:
            slot = slots_by_id.get(item["id"])
            if slot:
                changes["new_talks"].append(slot)

        for item in serialized["canceled_talks"]:
            slot = slots_by_id.get(item["id"])
            if slot:
                changes["canceled_talks"].append(slot)

        for item in serialized["moved_talks"]:
            submission = (
                submissions_by_code.get(item["submission_code"])
                if item["submission_code"]
                else None
            )
            new_slot = (
                slots_by_id.get(item["new_slot_id"]) if item["new_slot_id"] else None
            )

            if submission:
                from django.utils.dateparse import parse_datetime

                new_room = None
                old_room = None
                if item.get("new_room"):
                    new_room = rooms_by_id.get(item["new_room"])
                if item.get("old_room"):
                    old_room = rooms_by_id.get(item["old_room"])

                changes["moved_talks"].append(
                    {
                        "submission": submission,
                        "old_start": (
                            parse_datetime(item["old_start"])
                            if item["old_start"]
                            else None
                        ),
                        "new_start": (
                            parse_datetime(item["new_start"])
                            if item["new_start"]
                            else None
                        ),
                        "old_room": old_room,
                        "new_room": new_room,
                        "new_info": item["new_info"],
                        "new_slot": new_slot,
                    }
                )

        return changes

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
        cache_key = f"schedule_{self.id}_changes"
        cached_data = self.event.cache.get(cache_key)
        if cached_data:
            with suppress(json.JSONDecodeError, KeyError):
                serialized = json.loads(cached_data)
                return self._deserialize_changes(serialized)
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

        Slot = namedtuple("Slot", ["submission", "room", "local_start"])
        old_slots = {
            Slot(slot.submission, slot.room, slot.local_start): slot
            for slot in self.previous_schedule.scheduled_talks
        }
        new_slots = {
            Slot(slot.submission, slot.room, slot.local_start): slot
            for slot in self.scheduled_talks
        }

        old_slot_set = set(old_slots.keys())
        new_slot_set = set(new_slots.keys())
        old_submissions = {slot.submission for slot in old_slots}
        new_submissions = {slot.submission for slot in new_slots}
        handled_submissions = set()
        new_by_submission = defaultdict(list)
        old_by_submission = defaultdict(list)
        for slot in new_slot_set:
            new_by_submission[slot.submission].append(new_slots[slot])
        for slot in old_slot_set:
            old_by_submission[slot.submission].append(old_slots[slot])

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

        # WIP schedules: 60 seconds cache
        # Released schedules: 10 minutes cache
        timeout = 60 if self.version is None else 600

        with suppress(Exception):
            serialized = self._serialize_changes(result)
            self.event.cache.set(cache_key, json.dumps(serialized), timeout)

        return result

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
            notifications = render_notifications(
                data, event=self.event, speaker=speaker, locale=locale
            )
            slots = list(data.get("create") or []) + [
                talk["new_slot"] for talk in (data.get("update") or [])
            ]
            submissions = [slot.submission for slot in slots]
            mails.append(
                self.event.get_mail_template(MailTemplateRoles.NEW_SCHEDULE).to_mail(
                    user=speaker,
                    event=self.event,
                    context_kwargs={"user": speaker},
                    context={"notifications": notifications},
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
