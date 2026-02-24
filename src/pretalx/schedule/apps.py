# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import AppConfig


class ScheduleConfig(AppConfig):
    name = "pretalx.schedule"

    def ready(self):
        from . import (  # noqa: F401, PLC0415 -- register signals/receivers on startup
            signals,
        )
        from .phrases import (  # noqa: F401, PLC0415 -- register phrases on startup
            SchedulePhrases,
        )
