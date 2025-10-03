import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, PretalxTable
from pretalx.schedule.models import Room


class RoomTable(PretalxTable):
    name = tables.Column(
        linkify=lambda record: record.urls.settings_base,
        verbose_name=_("Name"),
        orderable=False,
    )
    capacity = tables.Column(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        default="",
        orderable=False,
    )
    actions = ActionsColumn(
        actions={
            "sort": {},
            "edit": {"url": "urls.settings_base"},
            "delete": {},
        }
    )
    empty_text = _("Please add at least one place in which sessions can take place.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs["dragsort-url"] = self.event.orga_urls.room_settings

    class Meta:
        model = Room
        fields = (
            "name",
            "capacity",
        )
        row_attrs = {"dragsort-id": lambda record: record.pk}
