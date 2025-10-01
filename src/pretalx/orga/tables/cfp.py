import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    BooleanIconColumn,
    PretalxTable,
    SortableColumn,
)
from pretalx.orga.utils.i18n import Translate
from pretalx.submission.models import (
    Question,
    SubmissionType,
    SubmitterAccessCode,
    Track,
)


class SubmitterAccessCodeTable(PretalxTable):
    code = tables.TemplateColumn(
        template_code="{% load copyable %}{{ record.code|copyable }}",
        verbose_name=_("Code"),
    )
    track = SortableColumn(
        linkify=lambda record: record.track and record.track.urls.base,
        verbose_name=_("Track"),
        order_by=Lower(Translate("track__name")),
    )
    submission_type = SortableColumn(
        linkify=lambda record: record.submission_type
        and record.submission_type.urls.base,
        verbose_name=_("Session type"),
        order_by=Lower(Translate("submission_type__name")),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.event.get_feature_flag("use_tracks"):
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


class TrackTable(PretalxTable):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs["dragsort-url"] = self.event.cfp.urls.tracks

    class Meta:
        model = Track
        fields = ("name", "color", "proposals", "actions")
        row_attrs = {"dragsort-id": lambda record: record.pk}


class SubmissionTypeTable(PretalxTable):
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

    class Meta:
        model = SubmissionType
        fields = ("name", "proposals", "default_duration", "actions")


class QuestionTable(PretalxTable):
    question = tables.Column(
        verbose_name=_("Custom field"),
        linkify=lambda record: record.urls.base,
        orderable=False,
    )
    target = tables.Column(verbose_name=_("Target"), orderable=False)
    variant = tables.Column(verbose_name=_("Field type"), orderable=False)
    required = BooleanIconColumn(orderable=False)
    active = BooleanIconColumn(orderable=False)
    answer_count = tables.Column(
        verbose_name=_("Responses"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        orderable=False,
    )
    actions = ActionsColumn(actions={"sort": {}, "edit": {}, "delete": {}})
    empty_text = _("You have configured no custom fields yet.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs["dragsort-url"] = self.event.cfp.urls.questions

    class Meta:
        model = Question
        fields = (
            "question",
            "target",
            "variant",
            "required",
            "active",
            "answer_count",
            "actions",
        )
        row_attrs = {"dragsort-id": lambda record: record.pk}
