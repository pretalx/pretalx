# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pretalx.common.components import component, register

component(
    "alert", "common/ui/alert.html", props=("id", "level"), defaults={"level": "info"}
)

__all__ = ["component", "register"]
