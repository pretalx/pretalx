# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.apps import AppConfig


class AgendaConfig(AppConfig):
    name = "pretalx.agenda"

    def ready(self):
        from .phrases import AgendaPhrases  # noqa: F401, PLC0415


with suppress(ImportError):
    from pretalx import celery_app as celery  # noqa: F401
