# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.orga.utils.i18n import Translate
from pretalx.person.models import SpeakerInformation, SpeakerProfile


class SpeakerInformationTable(PretalxTable):
    title = SortableColumn(
        linkify=lambda record: record.orga_urls.edit,
        verbose_name=_("Title"),
        order_by=Lower(Translate("title")),
    )
    resource = tables.Column(
        linkify=lambda record: record.resource.url if record.resource else None,
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exclude = list(self.exclude)
        if not self.event.get_feature_flag("use_tracks"):
            self.exclude.append("limit_tracks")

    def render_resource(self, record):
        return mark_safe('<i class="fa fa-file-o"></i>')

    class Meta:
        model = SpeakerInformation
        fields = (
            "title",
            "target_group",
            "limit_tracks",
            "limit_types",
            "resource",
        )


class SpeakerTable(PretalxTable):
    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        linkify=lambda record: record.orga_urls.base,
        accessor=("user__name"),
        empty_values=[""],
        order_by=Lower("user__name"),
        template_name="orga/includes/user_name.html",
        template_context={"user": lambda record, table: record.user},
    )
    accepted_submission_count = tables.Column(
        verbose_name=_("Accepted Proposals"),
        initial_sort_descending=True,
    )
    submission_count = tables.Column(
        verbose_name=_("Proposals"),
        initial_sort_descending=True,
    )
    has_arrived = TemplateColumn(
        verbose_name="", template_name="orga/tables/columns/speaker_arrived.html"
    )

    def __init__(self, *args, has_arrived_permission=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_arrived_permission = has_arrived_permission

    class Meta:
        model = SpeakerProfile
        fields = (
            "name",
            "accepted_submission_count",
            "submission_count",
            "has_arrived",
        )


class SpeakerOrgaTable(SpeakerTable):
    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        order_by=Lower("name"),
        template_name="orga/includes/user_name.html",
        context_object_name="user",
    )
    email = tables.Column(linkify=lambda record: f"mailto:{record.email}")
    has_arrived = None

    @cached_property
    def paginated_rows(self):
        # We need to cache this data to stay inside the scopes_disabled context
        return super().paginated_rows

    class Meta:
        model = SpeakerProfile
        fields = ("name", "email", "submission_count", "accepted_submission_count")
