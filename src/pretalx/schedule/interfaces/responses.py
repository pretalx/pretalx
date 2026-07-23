# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.http import HttpResponse

from pretalx.common.text.path import safe_filename
from pretalx.schedule.domain.ical import serialize_calendar


class CalendarResponse(HttpResponse):
    def __init__(self, calendar, filename, **kwargs):
        kwargs.setdefault("content_type", "text/calendar")
        super().__init__(serialize_calendar(calendar), **kwargs)
        self["Content-Disposition"] = (
            f'attachment; filename="{safe_filename(filename)}.ics"'
        )
