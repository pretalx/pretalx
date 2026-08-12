# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pretalx.common.components import component, register

component(
    "alert",
    "common/ui/alert.html",
    props=("id", "level"),
    slots=("actions",),
    defaults={"level": "info"},
)
component(
    "dialog",
    "common/ui/dialog.html",
    props=("id", "size", "label", "open", "body_id"),
    slots=("header", "body", "footer"),
)
component("page_heading", "common/ui/page_heading.html", slots=("buttons", "subtitle"))

__all__ = ["component", "register"]
