# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.common.forms.widgets import MarkdownWidget
from pretalx.common.templatetags.rich_text import render_markdown_plaintext


class BiographyWidget(MarkdownWidget):
    template_name = "common/widgets/biography.html"

    def __init__(self, suggestions=None, attrs=None):
        super().__init__(attrs)
        self.suggestions = suggestions or []

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        suggestions = []
        biographies = {}
        for s in self.suggestions:
            profile_id = str(s["id"])
            plaintext = render_markdown_plaintext(s["biography"])
            preview = plaintext[:200] + ("…" if len(plaintext) > 200 else "")
            suggestions.append(
                {"id": profile_id, "event_name": s["event_name"], "preview": preview}
            )
            biographies[profile_id] = s["biography"]
        ctx["suggestions"] = suggestions
        ctx["biographies"] = biographies
        return ctx

    class Media:
        js = [
            forms.Script("vendored/choices/choices.min.js", defer=""),
            forms.Script("common/js/forms/select.js", defer=""),
            forms.Script("common/js/forms/biography_suggestions.js", defer=""),
        ]
        css = {
            "all": ["vendored/choices/choices.min.css", "common/css/forms/select.css"]
        }
