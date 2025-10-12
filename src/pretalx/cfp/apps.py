# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import AppConfig


class CfPConfig(AppConfig):
    name = "pretalx.cfp"

    def ready(self):
        from .phrases import CfPPhrases  # noqa
