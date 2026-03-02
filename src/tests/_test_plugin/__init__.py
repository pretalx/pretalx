# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
# Fake plugin module for tests. Signal handlers registered via the
# register_signal_handler fixture have their __module__ set to this
# module's name so they pass EventPluginSignal._is_active without
# adding all of "tests" to CORE_MODULES.
