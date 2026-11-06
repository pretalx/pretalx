# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

# Test settings. Imported from pretalx.common.settings.test_settings which
# is included in pretalx so that plugins do not have to re-implement all
# test settings.

# ruff: noqa: F405

from pretalx.common.settings.test_settings import *  # noqa: F403

INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in PLUGINS]
INSTALLED_APPS += ["tests.dummy_app.PluginApp", "tests.dummy_app_no_hooks.PluginApp"]
PLUGINS = []
