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
    QuestionColumnMixin,
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

    @property
    def default_columns(self):
        columns = ["title", "limit_types", "limit_tracks", "resource"]
        if not self.event or not self.event.get_feature_flag("use_tracks"):
            columns.remove("limit_tracks")
        return columns

    class Meta:
        model = SpeakerInformation
        fields = (
            "title",
            "target_group",
            "limit_tracks",
            "limit_types",
            "resource",
        )


class SpeakerTable(QuestionColumnMixin, PretalxTable):
    default_columns = (
        "name",
        "submission_count",
        "accepted_submission_count",
        "has_arrived",
    )

    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        linkify=lambda record: record.orga_urls.base,
        accessor=("user__name"),
        empty_values=[""],
        order_by=Lower("user__name"),
        template_name="orga/includes/user_name.html",
        template_context={"user": lambda record, table: record.user},
    )
    code = tables.Column(
        verbose_name=_("ID"),
        accessor="user__code",
    )
    email = tables.Column(
        verbose_name=_("Email"),
        accessor="user__email",
        linkify=lambda record: record.orga_urls.send_mail,
    )
    submission_count = tables.Column(
        verbose_name=_("Proposals"),
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    accepted_submission_count = tables.Column(
        verbose_name=_("Accepted Proposals"),
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    locale = tables.Column(
        verbose_name=_("Language"),
        accessor="user__locale",
    )
    has_arrived = TemplateColumn(
        verbose_name=_("Arrived"),
        template_name="orga/tables/columns/speaker_arrived.html",
    )

    def __init__(
        self, *args, has_arrived_permission=False, short_questions=None, **kwargs
    ):
        self.short_questions = short_questions or []
        kwargs.setdefault("extra_columns", []).extend(self._get_question_columns())
        super().__init__(*args, **kwargs)
        self.has_arrived_permission = has_arrived_permission

    class Meta:
        model = SpeakerProfile
        fields = (
            "name",
            "code",
            "email",
            "submission_count",
            "accepted_submission_count",
            "locale",
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

    # Set unavailable columns to `None` so that the configuration form
    # won’t show up
    locale = None
    code = None
    has_arrived = None
    default_columns = None

    @cached_property
    def paginated_rows(self):
        # We need to cache this data to stay inside the scopes_disabled context
        return super().paginated_rows

    class Meta:
        model = SpeakerProfile
        fields = ("name", "email", "submission_count", "accepted_submission_count")
