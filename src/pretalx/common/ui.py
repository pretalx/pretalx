from django.template.loader import get_template

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
    ):
        self.label = label or self.label
        self.name = name
        self.value = value
        self.color = color or self.color
        self.size = size or self.size
        self.icon = icon or self.icon
        self.extra_classes = extra_classes
        self.type = _type or self._type
        self.template_context = (
            "label",
            "color",
            "size",
            "icon",
            "extra_classes",
            "name",
            "value",
            "type",
        )

    def __str__(self):
        return get_template(self.template_name).render(self.get_context())

    def get_context(self):
        return {attr: getattr(self, attr) for attr in self.template_context}


class LinkButton(Button):
    href = ""
    template_name = "common/ui/linkbutton.html"

    def __init__(self, *, href="", **kwargs):
        self.href = href
        super().__init__(**kwargs)
        self.template_context = (
            "label",
            "color",
            "size",
            "icon",
            "extra_classes",
            "href",
        )


def save_button():
    return Button()


def delete_button(href):
    return LinkButton(
        href=href,
        label=phrases.base.delete_button,
        color="outline-danger",
        icon="trash",
    )
