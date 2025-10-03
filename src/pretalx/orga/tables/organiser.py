import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, BooleanIconColumn, PretalxTable
from pretalx.event.models import Team


class TeamTable(PretalxTable):
    name = tables.TemplateColumn(
        linkify=lambda record: record.orga_urls.base,
        verbose_name=_("Name"),
        template_code='{% load i18n %}{{ record.name }} {% if request.user in record.members.all %}<i class="fa fa-star text-warning" title="{% translate "You are a member of this team" %}"></i>{% endif %}',
    )
    member_count = tables.Column(
        verbose_name=_("Members"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    all_events = BooleanIconColumn(verbose_name=_("All events"))
    is_reviewer = BooleanIconColumn(verbose_name=_("Reviewer"))
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.base"},
            "delete": {"url": "orga_urls.delete"},
        }
    )
    empty_text = _("Please add at least one place in which sessions can take place.")

    class Meta:
        model = Team
        fields = (
            "name",
            "member_count",
            "all_events",
            "is_reviewer",
            "actions",
        )
