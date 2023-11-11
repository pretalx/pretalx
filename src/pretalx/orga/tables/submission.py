from urllib.parse import quote

import django_tables2 as tables
from django.template import Context
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.submission.models import Submission


def get_header(request):
    return "hey"


class ContextTemplateColumn(tables.TemplateColumn):
    """Allow to change the context_object_name."""

    context_object_name = "record"

    def __init__(self, *args, **kwargs):
        if "context_object_name" in kwargs:
            self.context_object_name = kwargs.pop("context_object_name")
        super().__init__(*args, **kwargs)

    def render(self, record, table, value, bound_column, **kwargs):
        context = getattr(table, "context", Context())
        context[self.context_object_name] = record
        return super().render(record, table, value, bound_column, **kwargs)


class HelpTextMixin:
    def __init__(self, *args, help_text=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.help_text = help_text

    @property
    def header(self):
        if self.help_text:
            return mark_safe(
                f"{self.verbose_name} <i class='fa fa-question-circle' title='{self.help_text}'></i>"
            )
        return self.verbose_name


class ActionsColumn(tables.Column):
    attrs = {"td": {"class": "text-end action-column"}}
    empty_values = ()
    default_actions = {
        "edit": {
            "title": _("edit"),
            "icon": "edit",
            "url": "edit",
            "permission": None,
            "next": False,
            "color": "info",
        },
        "delete": {
            "title": _("Delete"),
            "icon": "trash",
            "url": "delete",
            "permission": None,
            "next": True,
            "color": "danger",
        },
    }

    def __init__(self, *args, actions=None, **kwargs):
        super().__init__(*args, **kwargs)

        # actions are defined by child classes as a dict of override settings,
        # mostly to set permissions and urls
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
            if user and action["permission"]:
                if not user.has_perm(action["permission"], record):
                    continue

            inner_html = (
                f'title="{action["title"]}" class="btn btn-sm btn-{action["color"]}">'
            )
            inner_html += f'<i class="fa fa-{action["icon"]}"></i>'

            # url is a dotted string to be accessed on the record
            url = action["url"]
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
                if action["next"] and request:
                    url = f"{url}?next={quote(request.get_full_path())}"
                html += f'<a href="{url}" {inner_html}</a>'
        return mark_safe(html)


class TemplateHelpTextColumn(HelpTextMixin, tables.TemplateColumn):
    pass


class SubmissionTable(tables.Table):
    indicator = tables.TemplateColumn(
        template_name="orga/tables/submission_side_indicator.html",
        orderable=False,
        verbose_name="",
        exclude_from_export=True,
    )
    title = tables.Column(
        linkify=lambda record: record.orga_urls.base,
        verbose_name=_("Title"),
        orderable=True,
    )
    speakers = tables.TemplateColumn(
        template_name="orga/tables/submission_speakers.html",
        verbose_name=_("Speakers"),
        orderable=True,
        order_by=("speakers__name"),
    )
    state = ContextTemplateColumn(
        template_name="orga/submission/state_dropdown.html",
        verbose_name=_("State"),
        orderable=True,
        context_object_name="submission",
    )
    submission_type = tables.Column(
        verbose_name=_("Type"),
        linkify=lambda record: record.submission_type.urls.base,
        accessor="submission_type.name",
        orderable=True,
        order_by=("submission_type__name"),
    )
    is_featured = TemplateHelpTextColumn(
        template_name="orga/tables/submission_is_featured.html",
        verbose_name=_("Featured"),
        orderable=True,
        help_text=_(
            "Show this session on the list of featured sessions, once it was accepted"
        ),
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(
        self,
        *args,
        event,
        can_view_speakers=False,
        can_change_submission=False,
        limit_tracks=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.exclude = list(self.exclude)  # Make sure we can add fields
        if not event.submission_types.all().count() > 1:
            self.exclude += ["submission_type"]
        if not can_view_speakers:
            self.exclude += ["speakers"]
        show_tracks = False
        if event.feature_flags["use_tracks"]:
            if limit_tracks:
                show_tracks = len(limit_tracks) > 1
            else:
                show_tracks = event.tracks.all().count() > 1
        if not show_tracks:
            self.exclude += ["track"]
        if not can_change_submission:
            self.exclude += ["is_featured", "actions"]

        # These values are only for exports
        self.columns.hide("code")
        self.columns.hide("track")
        self.columns.hide("is_anonymised")

    class Meta:
        model = Submission
        fields = (
            "code",
            "track",
            "is_anonymised",
            "indicator",
            "title",
            "speakers",
            "submission_type",
            "state",
            "is_featured",
            "actions",
        )
