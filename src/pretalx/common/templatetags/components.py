# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pretalx.common.components import component, register

component(
    "alert", "common/ui/alert.html", props=("id", "level"), defaults={"level": "info"}
)
component("dialog", "common/ui/dialog.html", props=("id", "size", "label", "open"))
component("dialog_header", "common/ui/dialog_header.html")
component("dialog_body", "common/ui/dialog_body.html", props=("id",))
component("dialog_footer", "common/ui/dialog_footer.html")

__all__ = ["component", "register"]
