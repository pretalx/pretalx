# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.plugins import get_all_plugins


def apply_plugin_changes(event, modules) -> None:
    """Fire install/uninstall hooks and persist ``modules`` as ``event.plugins``."""
    plugins_active = set(event.plugin_list)
    available = {plugin.module: plugin for plugin in get_all_plugins(event)}
    target = set(modules) & (available.keys() | plugins_active)
    if target == plugins_active:
        return

    for module in target - plugins_active:
        if hasattr(available[module].app, "installed"):
            available[module].app.installed(event)
    for module in plugins_active - target:
        if module in available and hasattr(available[module].app, "uninstalled"):
            available[module].app.uninstalled(event)

    event.plugins = ",".join(target)
    event.save(update_fields=["plugins"])


def enable_plugin(event, module: str, *, user=None) -> None:
    """Activate ``module`` on ``event`` (no-op if already active)."""
    if module in event.plugin_list:
        return
    apply_plugin_changes(event, [*event.plugin_list, module])
    event.log_action(
        "pretalx.event.plugins.enabled", person=user, data={"plugin": module}, orga=True
    )


def disable_plugin(event, module: str, *, user=None) -> None:
    """Deactivate ``module`` on ``event`` (no-op if not currently active)."""
    if module not in event.plugin_list:
        return
    apply_plugin_changes(event, [m for m in event.plugin_list if m != module])
    event.log_action(
        "pretalx.event.plugins.disabled",
        person=user,
        data={"plugin": module},
        orga=True,
    )
