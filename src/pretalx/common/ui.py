# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases


class Button:
    color = "success"
    extra_classes = ""
    icon = "check"
    size = "lg"
    label = phrases.base.save
    _type = "submit"
    template_name = "common/ui/button.html"

    def __init__(
        self,
        *,
        label="",
        color="",
        size="",
        icon="",
        extra_classes="",
        name="",
        value="",
        _type="",
        id=None,
    ):
        self.label = label or self.label
        self.name = name
        self.value = value
        self.color = color or self.color
        self.size = size or self.size
        self.icon = icon or (self.icon if icon is not None else None)
        self.extra_classes = extra_classes
        self.type = _type or self._type
        self.id = id
        self.template_context = (
            "label",
            "color",
            "size",
            "icon",
            "extra_classes",
            "name",
            "value",
            "type",
            "id",
        )

    def __str__(self):
        return get_template(self.template_name).render(self.get_context())

    def get_context(self):
        return {attr: getattr(self, attr) for attr in self.template_context}


class LinkButton(Button):
    href = ""
    template_name = "common/ui/linkbutton.html"

    def __init__(self, *, href="", icon=None, **kwargs):
        self.href = href
        super().__init__(icon=icon, **kwargs)
        self.template_context = (
            "label",
            "color",
            "size",
            "icon",
            "extra_classes",
            "href",
        )


def delete_link(href, label=None, color=None):
    return LinkButton(
        href=href,
        label=label or phrases.base.delete_button,
        color=color or "outline-danger",
        icon="trash",
    )


def delete_button(label=None, color=None):
    return Button(color="danger", icon="trash", label=phrases.base.delete_button)


def back_button(href):
    return LinkButton(
        href=href,
        icon=None,
        label=phrases.base.back_button,
        color="outline-info",
    )


def send_button():
    return Button(icon="envelope", label=phrases.base.send)


def api_buttons(event):
    return [
        LinkButton(
            href="https://docs.pretalx.org/api/",
            color="info",
            icon="book",
            label=_("Documentation"),
        ),
        LinkButton(href=event.api_urls.base, label=_("Go to API")),
    ]
