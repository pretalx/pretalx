# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import AppConfig


class OrgaConfig(AppConfig):
    name = "pretalx.orga"

    def ready(self):
        from . import permissions  # noqa: F401, PLC0415
        from . import receivers  # noqa: F401, PLC0415
        from . import signals  # noqa: F401, PLC0415
        from .phrases import OrgaPhrases  # noqa: F401, PLC0415
