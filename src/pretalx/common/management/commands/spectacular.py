# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""
Overriding the default OpenAPI schema generation in order to
disable scope checks on schema generation.
"""

from django_scopes import scopes_disabled
from drf_spectacular.management.commands.spectacular import Command as Parent


class Command(Parent):
    def handle(self, *args, **kwargs):
        with scopes_disabled():
            return super().handle(*args, **kwargs)
