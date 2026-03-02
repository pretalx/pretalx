# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django.apps import AppConfig


class PluginApp(AppConfig):
    name = "tests.dummy_app_no_hooks"
    verbose_name = "Test Dummy Plugin (No Hooks)"

    class PretalxPluginMeta:
        name = "Test Dummy Plugin (No Hooks)"
        author = "Test"
        description = "Dummy plugin without installed/uninstalled hooks"
        visible = True
        version = "0.0.0"
        category = "OTHER"
