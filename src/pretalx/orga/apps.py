# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import AppConfig


class OrgaConfig(AppConfig):
    name = "pretalx.orga"

    def ready(self):
        from . import permissions  # noqa
        from . import receivers  # noqa
        from . import signals  # noqa
        from .phrases import OrgaPhrases  # noqa
