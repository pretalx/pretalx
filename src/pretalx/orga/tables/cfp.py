import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn
from pretalx.submission.models import SubmissionType, SubmitterAccessCode, Track


class SubmitterAccessCodeTable(tables.Table):
    code = tables.TemplateColumn(
        template_code="{% load copyable %}{{ record.code|copyable }}",
        verbose_name=_("Code"),
    )
    track = tables.Column(
        linkify=lambda record: record.track and record.track.urls.base,
        verbose_name=_("Track"),
        order_by="track__name",
    )
    submission_type = tables.Column(
        linkify=lambda record: record.submission_type
        and record.submission_type.urls.base,
        verbose_name=_("Session type"),
        order_by="submission_type__name",
    )
    uses = tables.TemplateColumn(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        template_code="{{ record.redeemed|default:0 }} / {{ record.maximum_uses|default:'∞ '}}",
        order_by="redeemed",
    )
    actions = ActionsColumn(
        actions={
            "copy": {
                "extra_attrs": lambda record: f'role="button" data-destination="{record.urls.cfp_url.full()}"',
                "title": _("Copy access code link"),
            },
            "send": {
                "title": _("Send access code as email"),
            },
            "edit": {},
            "delete": {
                "condition": lambda record: not record.submissions.exists(),
            },
        }
    )
    empty_text = _("Please add at least one place in which sessions can take place.")

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not event.get_feature_flag("use_tracks"):
            self.columns["track"].hide()

    class Meta:
        model = SubmitterAccessCode
        fields = (
            "code",
            "track",
            "submission_type",
            "uses",
            "actions",
        )


class TrackTable(tables.Table):
    name = tables.TemplateColumn(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Track"),
        template_code='{{ record.name }} {% if record.requires_access_code %}{% load i18n %}<i class="fa fa-lock ml-1" title="{% translate "Requires access code" %}"></i>{% endif %}',
        orderable=False,
    )
    color = tables.TemplateColumn(
        verbose_name=_("Colour"),
        template_code='<div class="color-square" style="background: {{ record.color }}"></div>',
        orderable=False,
    )
    proposals = tables.TemplateColumn(
        verbose_name=_("Proposals"),
        linkify=lambda record: f"{record.event.orga_urls.submissions}?track={record.id}",
        template_code="{{ record.submissions.all.count }}",
        orderable=False,
    )
    actions = ActionsColumn(
        actions={
            "sort": {},
            "link": {
                "title": _("Go to pre-filled CfP form"),
                "icon": "link",
                "url": "urls.prefilled_cfp.full",
                "color": "info",
            },
            "edit": {},
            "delete": {},
        }
    )

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs["dragsort-url"] = event.cfp.urls.tracks

    class Meta:
        model = Track
        fields = ("name", "color", "proposals", "actions")
        row_attrs = {"dragsort-id": lambda record: record.pk}


class SubmissionTypeTable(tables.Table):
    name = tables.TemplateColumn(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Session type"),
        template_code='{{ record.name }} {% if record.requires_access_code %}{% load i18n %}<i class="fa fa-lock ml-1" title="{% translate "Requires access code" %}"></i>{% endif %}',
    )
    proposals = tables.TemplateColumn(
        verbose_name=_("Proposals"),
        linkify=lambda record: f"{record.event.orga_urls.submissions}?submission_type={record.id}",
        template_code="{{ record.submissions.all.count }}",
        order_by="submission_count",
    )
    actions = ActionsColumn(
        actions={
            "default": {
                "url": "urls.default",
                "color": "info",
                "label": _("Make default"),
                "condition": lambda record: not record.event.cfp.default_type == record,
                "next_url": True,
            },
            "link": {
                "title": _("Go to pre-filled CfP form"),
                "icon": "link",
                "url": "urls.prefilled_cfp.full",
                "color": "info",
            },
            "edit": {},
            "delete": {},
        }
    )

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = SubmissionType
        fields = ("name", "proposals", "default_duration", "actions")
