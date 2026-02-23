# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "pretalx.common"

    def ready(self):
        from . import (  # noqa: F401, PLC0415
            checks,
            log_display,
            signals,
            update_check,
        )


with suppress(ImportError):
    from pretalx import celery_app as celery  # noqa: F401
