# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import AppConfig


class PersonConfig(AppConfig):
    name = "pretalx.person"

    def ready(self):
        from . import signals  # noqa
