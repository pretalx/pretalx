# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Andreas Hubel

import datetime as dt
import json

from django.template.loader import get_template
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from i18nfield.utils import I18nJSONEncoder

from pretalx import __version__
from pretalx.common.exporter import BaseExporter
from pretalx.common.urls import get_base_url, get_netloc
from pretalx.schedule.ical import get_slots_ical


class ScheduleData(BaseExporter):
    def __init__(self, event, schedule=None, with_accepted=False, with_breaks=False):
        super().__init__(event)
        self.schedule = schedule
        self.with_accepted = with_accepted
        self.with_breaks = with_breaks

    @cached_property
    def metadata(self):
        if not self.schedule:
            return []

        return {
            "url": self.event.urls.schedule.full(),
            "base_url": get_base_url(self.event),
        }

    @cached_property
    def data(self):
        if not self.schedule:
            return []

        event = self.event
        schedule = self.schedule

        base_qs = (
            schedule.talks.all()
            if self.with_accepted
            else schedule.talks.filter(is_visible=True)
        )
        talks = (
            base_qs.select_related(
                "submission",
                "submission__event",
                "submission__submission_type",
                "submission__track",
                "room",
            )
            .prefetch_related("submission__speakers")
            .order_by("start")
            .exclude(submission__state="deleted")
        )
        data = {
            current_date.date(): {
                "index": index + 1,
                "start": current_date.replace(hour=4, minute=0).astimezone(event.tz),
                "end": current_date.replace(hour=3, minute=59).astimezone(event.tz)
                + dt.timedelta(days=1),
                "first_start": None,
                "last_end": None,
                "rooms": {},
            }
            for index, current_date in enumerate(
                event.datetime_from + dt.timedelta(days=days)
                for days in range((event.date_to - event.date_from).days + 1)
            )
        }

        for talk in talks:
            if (
                not talk.start
                or not talk.room
                or (not talk.submission and not self.with_breaks)
            ):
                continue
            talk_date = talk.local_start.date()
            if talk.local_start.hour < 3 and talk_date != event.date_from:
                talk_date -= dt.timedelta(days=1)
            day_data = data.get(talk_date)
            if not day_data:
                continue
            if str(talk.room.name) not in day_data["rooms"]:
                day_data["rooms"][str(talk.room.name)] = {
                    "id": talk.room.id,
                    "guid": talk.room.uuid,
                    "name": talk.room.name,
                    "description": talk.room.description,
                    "position": talk.room.position,
                    "talks": [talk],
                }
            else:
                day_data["rooms"][str(talk.room.name)]["talks"].append(talk)
            if not day_data["first_start"] or talk.start < day_data["first_start"]:
                day_data["first_start"] = talk.start
            if not day_data["last_end"] or talk.local_end > day_data["last_end"]:
                day_data["last_end"] = talk.local_end

        for day in data.values():
            day["rooms"] = sorted(
                day["rooms"].values(),
                key=lambda room: (
                    room["position"] if room["position"] is not None else room["id"]
                ),
            )
        return data.values()


class FrabXmlExporter(ScheduleData):
    verbose_name = "XML (frab compatible)"
    public = True
    show_qrcode = True
    icon = "fa-code"
    cors = "*"
    extension = "xml"
    filename_identifier = "schedule"
    content_type = "text/xml"

    def get_data(self, **kwargs):
        context = {
            "data": self.data,
            "metadata": self.metadata,
            "schedule": self.schedule,
            "event": self.event,
            "version": __version__,
            "base_url": get_base_url(self.event),
        }
        return get_template("agenda/schedule.xml").render(context=context)


class FrabXCalExporter(ScheduleData):
    verbose_name = "XCal (frab compatible)"
    public = True
    icon = "fa-calendar"
    cors = "*"
    filename_identifier = "schedule"
    extension = "xcal"
    content_type = "text/xml"

    def get_data(self, **kwargs):
        url = get_base_url(self.event)
        context = {"data": self.data, "url": url, "domain": get_netloc(self.event)}
        return get_template("agenda/schedule.xcal").render(context=context)


class FrabJsonExporter(ScheduleData):
    verbose_name = "JSON (frab compatible)"
    public = True
    icon = "{ }"
    cors = "*"
    filename_identifier = "schedule"
    extension = "json"
    content_type = "application/json"

    def _get_data(self, **kwargs):
        schedule = self.schedule
        return {
            "url": self.metadata["url"],
            "version": schedule.version,
            "base_url": self.metadata["base_url"],
            "conference": {
                "acronym": self.event.slug,
                "title": str(self.event.name),
                "start": self.event.date_from.strftime("%Y-%m-%d"),
                "end": self.event.date_to.strftime("%Y-%m-%d"),
                "daysCount": self.event.duration,
                "timeslot_duration": "00:05",
                "time_zone_name": self.event.timezone,
                "colors": {"primary": self.event.primary_color or "#3aa57c"},
                "rooms": [
                    {
                        "name": str(room.name),
                        "slug": room.slug,
                        # TODO room url
                        "guid": room.uuid,
                        "description": str(room.description) or None,
                        "capacity": room.capacity,
                    }
                    for room in self.event.rooms.all()
                ],
                "tracks": [
                    {
                        "name": str(track.name),
                        "slug": track.slug,
                        "color": track.color,
                    }
                    for track in self.event.tracks.all()
                ],
                "days": [
                    {
                        "index": day["index"],
                        "date": day["start"].strftime("%Y-%m-%d"),
                        "day_start": day["start"].astimezone(self.event.tz).isoformat(),
                        "day_end": day["end"].astimezone(self.event.tz).isoformat(),
                        "rooms": {
                            str(room["name"]): [
                                {
                                    "guid": talk.uuid,
                                    "code": talk.submission.code,
                                    "id": talk.submission.id,
                                    "logo": (
                                        talk.submission.urls.image.full()
                                        if talk.submission.image
                                        else None
                                    ),
                                    "date": talk.local_start.isoformat(),
                                    "start": talk.local_start.strftime("%H:%M"),
                                    "duration": talk.export_duration,
                                    "room": str(room["name"]),
                                    "slug": talk.frab_slug,
                                    "url": talk.submission.urls.public.full(),
                                    "title": talk.submission.title,
                                    "subtitle": "",
                                    "track": (
                                        str(talk.submission.track.name)
                                        if talk.submission.track
                                        else None
                                    ),
                                    "type": str(talk.submission.submission_type.name),
                                    "language": talk.submission.content_locale,
                                    "abstract": talk.submission.abstract,
                                    "description": talk.submission.description,
                                    "recording_license": "",
                                    "do_not_record": talk.submission.do_not_record,
                                    "persons": [
                                        {
                                            "code": person.code,
                                            "name": person.get_display_name(),
                                            "avatar": person.get_avatar_url(self.event)
                                            or None,
                                            "biography": person.event_profile(
                                                self.event
                                            ).biography,
                                            "public_name": person.get_display_name(),  # deprecated
                                            "guid": person.guid,
                                            "url": person.event_profile(
                                                self.event
                                            ).urls.public.full(),
                                        }
                                        for person in talk.submission.speakers.all()
                                    ],
                                    "links": [
                                        {
                                            "title": resource.description,
                                            "url": resource.link,
                                            "type": "related",
                                        }
                                        for resource in talk.submission.resources.all()
                                        if resource.link
                                    ],
                                    "feedback_url": talk.submission.urls.feedback.full(),
                                    "origin_url": talk.submission.urls.public.full(),
                                    "attachments": [
                                        {
                                            "title": resource.description,
                                            "url": resource.resource.url,
                                            "type": "related",
                                        }
                                        for resource in talk.submission.resources.all()
                                        if not resource.link
                                    ],
                                }
                                for talk in room["talks"]
                            ]
                            for room in day["rooms"]
                        },
                    }
                    for day in self.data
                ],
            },
        }

    def get_data(self, **kwargs):
        return json.dumps(
            {
                "$schema": "https://c3voc.de/schedule/schema.json",
                "generator": {"name": "pretalx", "version": __version__},
                "schedule": self._get_data(**kwargs),
            },
            cls=I18nJSONEncoder,
        )


class ICalExporter(BaseExporter):
    verbose_name = _("iCal (full event)")
    public = True
    show_public = False
    show_qrcode = True
    icon = "fa-calendar"
    cors = "*"
    filename_identifier = "schedule"
    extension = "ics"
    content_type = "text/calendar"

    def __init__(self, event, schedule=None):
        super().__init__(event)
        self.schedule = schedule

    def get_data(self, **kwargs):
        talks = (
            self.schedule.talks.filter(is_visible=True)
            .prefetch_related("submission__speakers")
            .select_related("submission", "room", "submission__event")
            .order_by("start")
        )
        return get_slots_ical(self.schedule.event, talks).serialize()


class FavedICalExporter(BaseExporter):
    identifier = "faved.ics"
    verbose_name = _("iCal (your starred sessions)")
    show_qrcode = False
    icon = "fa-calendar"
    show_public = True
    cors = "*"
    filename_identifier = "faved"
    extension = "ics"
    content_type = "text/calendar"

    def is_public(self, request, **kwargs):
        return (
            "agenda" in request.resolver_match.namespaces
            and request.user.is_authenticated
            and request.user.has_perm("schedule.list_schedule", request.event)
        )

    def get_data(self, request, **kwargs):
        if not request.user.is_authenticated:
            return None

        slots = request.event.current_schedule.scheduled_talks.filter(
            submission__favourites__user__in=[request.user]
        )
        return get_slots_ical(request.event, slots, prodid_suffix="faved").serialize()
