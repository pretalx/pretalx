# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from django.forms import CheckboxSelectMultiple, RadioSelect
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    add_attribute,
)


class PluginSelectWidget(CheckboxSelectMultiple):
    template_name = "orga/widgets/plugin_select.html"
    option_template_name = "orga/widgets/plugin_option.html"

    def __init__(self, *args, plugins=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plugins = {p.module: p for p in (plugins or [])}

    class Media:
        css = {"all": ["orga/css/ui/plugins.css"]}

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        opt = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        opt["plugin"] = self.plugins.get(value)
        return opt


class HeaderSelect(RadioSelect):
    option_template_name = "orga/widgets/header_option.html"

    class Media:
        css = {
            "all": [
                "common/css/headers/pcb.css",
                "common/css/headers/bubbles.css",
                "common/css/headers/signal.css",
                "common/css/headers/topo.css",
                "common/css/headers/graph.css",
                "orga/css/forms/header.css",
            ]
        }


class LanguageWidgetMixin:
    css_class = "language-select"
    search_fields = "label,customProperties"
    official_group_label = _("Official translations")
    community_group_label = _("Community translations")
    community_note = _(
        "These translations are not maintained by the pretalx project. "
        "We cannot vouch for their correctness and new or recently changed "
        "features might not be translated and will show in English instead. "
        "You can improve community translations at translate.pretalx.com."
    )

    @property
    def community_label(self):
        return f"{self.community_group_label}\n{self.community_note}"

    def optgroups(self, name, value, attrs=None):
        official = []
        community = []
        for index, (option_value, option_label) in enumerate(self.choices):
            language = settings.LANGUAGES_INFORMATION[option_value]
            group = official if language.get("official") else community
            group.append(
                self.create_option(
                    name,
                    option_value,
                    option_label,
                    str(option_value) in value,
                    index,
                    attrs=attrs,
                )
            )
        groups = []
        for label, options in (
            (self.official_group_label, official),
            (self.community_label, community),
        ):
            if options:
                groups.append((str(label), options, len(groups)))
        return groups

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        language = settings.LANGUAGES_INFORMATION[value]
        option["attrs"]["lang"] = value
        option["attrs"]["data-custom-properties"] = language["natural_name"]
        if not language.get("official") and (percentage := language.get("percentage")):
            option["attrs"]["data-description"] = _("%(percentage)s %% translated") % {
                "percentage": percentage
            }
        return option

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        widget["attrs"] = add_attribute(widget["attrs"], "class", self.css_class)
        widget["attrs"]["data-search-fields"] = self.search_fields
        return context


class MultipleLanguagesWidget(LanguageWidgetMixin, EnhancedSelectMultiple):
    pass


class LanguageWidget(LanguageWidgetMixin, EnhancedSelect):
    pass


class FontSelect(EnhancedSelect):
    def __init__(self, attrs=None, choices=(), fonts=None, default_font=None):
        super().__init__(attrs, choices)
        self.fonts = fonts or {}
        self.default_font = default_font

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if value and value in self.fonts:
            option["attrs"]["data-font-family"] = value
            sample = self.fonts[value].get("sample", "")
            if sample:
                option["attrs"]["data-font-sample"] = sample
        elif not value and self.default_font:
            option["attrs"]["data-font-family"] = self.default_font
        return option
