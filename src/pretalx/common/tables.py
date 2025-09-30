from urllib.parse import quote

import django_tables2 as tables
from django.template import Context
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


class ActionsColumn(tables.Column):
    attrs = {"td": {"class": "text-end"}}
    empty_values = ()
    default_actions = {
        "edit": {
            "title": _("edit"),
            "icon": "edit",
            "url": "edit",
            "color": "info",
        },
        "delete": {
            "title": _("Delete"),
            "icon": "trash",
            "url": "delete",
            "next_url": True,
            "color": "danger",
        },
        "sort": {
            "title": _("Move item"),
            "icon": "arrows",
            "color": "primary",
            "extra_class": "dragsort-button",
            "extra_attrs": 'draggable="true"',
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

            extra_class = action.get("extra_class") or ""
            extra_class = f" {extra_class}" if extra_class else ""
            extra_attrs = action.get("extra_attrs") or ""
            extra_attrs = f" {extra_attrs}" if extra_attrs else ""
            inner_html = f'title="{action["title"]}" class="btn btn-sm btn-{action["color"]}{extra_class}"{extra_attrs}>'
            inner_html += f'<i class="fa fa-{action["icon"]}"></i>'

            # url is a dotted string to be accessed on the record
            url = action.get("url")
            if not url:
                # Render button and hope there is some JS to handle it
                html += f"<button {inner_html}</button>"
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
