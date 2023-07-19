# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

from django.apps import AppConfig


class EventConfig(AppConfig):
    name = "pretalx.event"

    def ready(self):
        from . import services  # noqa
