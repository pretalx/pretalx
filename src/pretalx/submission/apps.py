# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import AppConfig


class SubmissionConfig(AppConfig):
    name = "pretalx.submission"

    def ready(self):
        from . import exporters  # noqa: F401, PLC0415
        from . import rules  # noqa: F401, PLC0415
        from . import signals  # noqa: F401, PLC0415
        from .phrases import SubmissionPhrases  # noqa: F401, PLC0415
