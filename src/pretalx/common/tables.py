from urllib.parse import quote

import django_tables2 as tables
from django.template import Context
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_tables2.utils import AttributeDict


def get_icon(icon):
    return mark_safe(f'<i class="fa fa-{icon}"></i>')


class ActionsColumn(tables.Column):
    attrs = {"td": {"class": "text-end"}}
    empty_values = ()
    default_actions = {
        "edit": {
            "title": _("edit"),
            "icon": "edit",
            "url": "urls.edit",
            "color": "info",
            "condition": None,
        },
        "delete": {
            "title": _("Delete"),
            "icon": "trash",
            "url": "urls.delete",
            "next_url": True,
            "color": "danger",
            "condition": None,
        },
        "sort": {
            "title": _("Move item"),
            "icon": "arrows",
            "color": "primary",
            "extra_class": "dragsort-button",
            "extra_attrs": 'draggable="true"',
            "condition": None,
        },
        "copy": {
            "icon": "copy",
            "title": _("Copy access code link"),
            "extra_class": "copyable-text",
            "color": "info",
        },
        "send": {
            "icon": "envelope",
            "color": "info",
            "url": "urls.send",
        },
    }

    def __init__(self, *args, actions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable = False

        self.actions = {}
        for key, value in actions.items():
            self.actions[key] = self.default_actions.get(key, {}).copy()
            self.actions[key].update(value)

    def header(self):
        # Don't ever show a column title
        return ""

    def render(self, record, table, **kwargs):
        if not self.actions or not getattr(record, "pk", None):
            return ""

        request = getattr(table, "context", {}).get("request")
        user = getattr(request, "user", None)

        html = ""
        for action in self.actions.values():
            if user and (permission := action.get("permission")):
                if not user.has_perm(permission, record):
                    continue
            if (condition := action.get("condition")) and not condition(record):
                continue

            extra_class = action.get("extra_class") or ""
            extra_class = f" {extra_class}" if extra_class else ""
            extra_attrs = action.get("extra_attrs") or ""
            if callable(extra_attrs):
                extra_attrs = extra_attrs(record)
            extra_attrs = f" {extra_attrs}" if extra_attrs else ""
            inner_html = ""
            if title := action.get("title"):
                inner_html += f'title="{title}" '
            inner_html += (
                f'class="btn btn-sm btn-{action["color"]}{extra_class}"{extra_attrs}>'
            )
            if icon := action.get("icon"):
                inner_html += get_icon(icon)
            if label := action.get("label"):
                inner_html += label

            # url is a dotted string to be accessed on the record
            url = action.get("url")
            if not url:
                # Render button and hope there is some JS to handle it
                html += f"<button {inner_html}</button>"
            else:
                if callable(url):
                    url = url(record)
                else:
                    url_parts = url.split(".")
                    url = record
                    for part in url_parts:
                        url = getattr(url, part)
                        if callable(url):
                            url = url()
                if action.get("next_url") and request:
                    url = f"{url}?next={quote(request.get_full_path())}"
                html += f'<a href="{url}" {inner_html}</a>'
        html = f'<div class="action-column">{html}</div>'
        return mark_safe(html)


class ContextTemplateColumn(tables.TemplateColumn):
    """Allow to change the context_object_name."""

    context_object_name = "record"

    def __init__(self, *args, **kwargs):
        if name := kwargs.pop("context_object_name", None):
            self.context_object_name = name
        super().__init__(*args, **kwargs)

    def render(self, record, table, value, bound_column, **kwargs):
        context = getattr(table, "context", Context())
        context[self.context_object_name] = record
        return super().render(record, table, value, bound_column, **kwargs)


class BooleanIconColumn(tables.BooleanColumn):
    attrs = {
        "td": {"class": "text-center"},
        "th": {"class": "text-center"},
    }

    def __init__(self, *args, yesno=None, **kwargs):
        yesno = get_icon("check-circle text-success"), get_icon(
            "times-circle text-danger"
        )
        super().__init__(*args, yesno=yesno, attrs=self.attrs, **kwargs)

    def render(self, value, record, bound_column):
        # We do not escape the yesno value because we know it's safe
        value = self._get_bool_value(record, value, bound_column)
        text = self.yesno[int(not value)]
        attrs = self.attrs
        attrs["td"]["class"] += f" {str(value).lower()}"
        return format_html("<span {}>{}</span>", AttributeDict(attrs).as_html(), text)
