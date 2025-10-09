import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
)
from pretalx.orga.utils.i18n import Translate
from pretalx.person.models import SpeakerInformation, SpeakerProfile


class SpeakerInformationTable(PretalxTable):
    title = SortableColumn(
        linkify=lambda record: record.orga_urls.edit,
        verbose_name=_("Title"),
        order_by=Lower(Translate("title")),
    )
    resource = tables.TemplateColumn(
        linkify=lambda record: record.resource.url if record.resource else None,
        template_code='<i class="fa fa-file-o"></i>',
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.event.get_feature_flag("use_tracks"):
            self.columns["limit_tracks"].hide()

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
        order_by=Lower("user__name"),
        template_code='{% include "orga/includes/user_name.html" with user=record.user %}',
    )
    accepted_submission_count = tables.Column(verbose_name=_("Accepted Proposals"))
    submission_count = tables.Column(verbose_name=_("Proposals"))
    has_arrived = tables.TemplateColumn(
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
