# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "pretalx.common"

    def ready(self):
        from . import checks  # noqa: F401, PLC0415
        from . import log_display  # noqa: F401, PLC0415
        from . import signals  # noqa: F401, PLC0415
        from . import update_check  # noqa: F401, PLC0415


with suppress(ImportError):
    from pretalx import celery_app as celery  # noqa: F401
