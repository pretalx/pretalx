# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    BooleanColumn,
    DateTimeColumn,
    PretalxTable,
    SortableColumn,
    TemplateColumn,
    UnsortableMixin,
)
from pretalx.orga.utils.i18n import Translate
from pretalx.submission.models import (
    Question,
    SubmissionType,
    SubmitterAccessCode,
    Track,
)


class SubmitterAccessCodeTable(PretalxTable):
    code = TemplateColumn(
        template_name="orga/tables/columns/copyable.html",
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
    valid_until = tables.Column()
    uses = tables.Column(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        order_by="redeemed",
        empty_values=[""],
        initial_sort_descending=True,
    )

    def render_uses(self, record):
        redeemed = record.redeemed or 0
        maximum = record.maximum_uses if record.maximum_uses else "∞ "
        return f"{redeemed} / {maximum}"

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

    def render_valid_until(self, record):
        return record.valid_until.strftime("%Y-%m-%d %H:%M")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exclude = list(self.exclude)
        if not self.event.get_feature_flag("use_tracks"):
            self.exclude.append("track")

    class Meta:
        model = SubmitterAccessCode
        fields = (
            "code",
            "track",
            "submission_type",
            "valid_until",
            "uses",
            "actions",
        )


class TrackTable(UnsortableMixin, PretalxTable):
    default_columns = (
        "name",
        "color",
        "proposals",
    )

    name = tables.Column(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Track"),
    )
    color = TemplateColumn(
        template_name="orga/tables/columns/color_square.html",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    proposals = tables.Column(
        verbose_name=_("Proposals"),
        linkify=lambda record: f"{record.event.orga_urls.submissions}?track={record.id}",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        accessor="submission_count",
    )
    requires_access_code = BooleanColumn()
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
        fields = (
            "name",
            "color",
            "proposals",
            "requires_access_code",
            "actions",
        )
        row_attrs = {"dragsort-id": lambda record: record.pk}


class SubmissionTypeTable(PretalxTable):
    default_columns = (
        "name",
        "proposals",
        "default_duration",
    )

    name = TemplateColumn(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Session type"),
        template_name="orga/tables/columns/submission_type_name.html",
    )
    proposals = tables.Column(
        verbose_name=_("Proposals"),
        linkify=lambda record: f"{record.event.orga_urls.submissions}?submission_type={record.id}",
        accessor="submission_count",
        order_by="submission_count",
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    deadline = DateTimeColumn(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    default_duration = tables.Column(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    requires_access_code = BooleanColumn()
    actions = ActionsColumn(
        actions={
            "default": {
                "url": "urls.default",
                "color": "info",
                "label": _("Make default"),
                "condition": lambda record: record.event.cfp.default_type != record,
                "permission": "update",
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
        fields = (
            "name",
            "default_duration",
            "proposals",
            "deadline",
            "requires_access_code",
            "actions",
        )


class QuestionTable(UnsortableMixin, PretalxTable):
    question = tables.Column(
        verbose_name=_("Custom field"),
        linkify=lambda record: record.urls.base,
    )
    target = tables.Column(verbose_name=_("Target"))
    variant = tables.Column(verbose_name=_("Field type"))
    required = BooleanColumn()
    active = BooleanColumn()
    answer_count = tables.Column(
        verbose_name=_("Responses"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        initial_sort_descending=True,
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
