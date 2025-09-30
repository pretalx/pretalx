import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn
from pretalx.person.models import SpeakerInformation


class SpeakerInformationTable(tables.Table):
    title = tables.Column(
        linkify=lambda record: record.orga_urls.edit,
        verbose_name=_("Title"),
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

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not event.get_feature_flag("use_tracks"):
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
