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
    props=("id", "size", "label", "open", "body_id", "content_id"),
    slots=("header", "body", "footer"),
    defaults={"content_id": ""},
)
component(
    "dropdown_menu",
    "common/ui/dropdown_menu.html",
    props=("id", "label", "align", "trigger_class", "caret"),
    slots=("trigger",),
    defaults={"align": "se", "caret": "caret-down"},
)
component(
    "dropdown_menu_entry",
    "common/ui/dropdown_menu_entry.html",
    props=(
        "href",
        "icon",
        "label",
        "danger",
        "target",
        "type",
        "extra_class",
        "title",
        "attrs",
    ),
    defaults={"type": "submit"},
)
component(
    "filter_page_content",
    "common/ui/filter_page_content.html",
    props=("table_name", "extra_class"),
    defaults={"extra_class": ""},
)
component(
    "form_row",
    "common/ui/form_row.html",
    props=("label_id", "row_class", "value_class", "required"),
    slots=("label", "field"),
    defaults={"required": None},
)
component("page_heading", "common/ui/page_heading.html", slots=("buttons", "subtitle"))

__all__ = ["component", "register"]
