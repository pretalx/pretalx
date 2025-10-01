import django_tables2 as tables
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, PretalxTable, SortableTemplateColumn
from pretalx.person.models import User


class AdminUserTable(PretalxTable):
    name = SortableTemplateColumn(
        linkify=lambda record: reverse(
            "orga:admin.user.detail", kwargs={"code": record.code}
        ),
        template_code='{% include "orga/includes/user_name.html" with user=record %}',
    )
    email = SortableTemplateColumn(
        template_code="{% load copyable %}{{ record.email|copyable }}",
    )
    teams = tables.TemplateColumn(
        template_code='<ul>{% for team in record.teams.all %}<li><a href="{{ team.urls.base }}">{{ team.name }}</a></li>{% endfor %}',
        verbose_name=_("Teams"),
        orderable=False,
    )
    events = tables.TemplateColumn(
        template_code='<ul>{% for event in record.get_events_with_any_permission %}<li><a href="{{ event.orga_urls.base }}">{{ event.name }}</a></li>{% endfor %}',
        orderable=False,
    )
    submission_count = tables.Column(
        verbose_name=_("Submissions"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    last_login = tables.TemplateColumn(
        template_code="{% load i18n %}{{ record.last_login|timesince }} {% if record.last_login %}{% translate 'ago'%}{% endif %}",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    pw_reset_time = tables.TemplateColumn(
        template_code="{% load i18n %}{{ record.pw_reset_time|timesince }} {% if record.pw_reset_time %}{% translate 'ago'%}{% endif %}",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    actions = ActionsColumn(
        actions={
            "edit": {
                "url": lambda record: reverse(
                    "orga:admin.user.detail", kwargs={"code": record.code}
                )
            },
            "delete": {
                "url": lambda record: reverse(
                    "orga:admin.user.delete", kwargs={"code": record.code}
                )
            },
        }
    )

    class Meta:
        model = User
        fields = (
            "name",
            "email",
            "locale",
            "teams",
            "events",
            "submission_count",
            "last_login",
            "pw_reset_time",
            "actions",
        )
