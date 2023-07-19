# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

from django.apps import AppConfig


class SubmissionConfig(AppConfig):
    name = "pretalx.submission"

    def ready(self):
        from . import exporters  # noqa
        from . import permissions  # noqa
        from . import signals  # noqa
