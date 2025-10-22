# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    PretalxTable,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.person.models import User


class AdminUserTable(PretalxTable):
    name = TemplateColumn(
        linkify=lambda record: reverse(
            "orga:admin.user.detail", kwargs={"code": record.code}
        ),
        template_name="orga/includes/user_name.html",
        context_object_name="user",
    )
    email = SortableTemplateColumn(
        template_name="orga/tables/columns/copyable.html",
    )
    teams = TemplateColumn(
        template_name="orga/tables/columns/admin_user_teams.html",
        verbose_name=_("Teams"),
        orderable=False,
    )
    events = TemplateColumn(
        template_name="orga/tables/columns/admin_user_events.html",
        orderable=False,
    )
    submission_count = tables.Column(
        verbose_name=_("Submissions"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        initial_sort_descending=True,
    )
    last_login = TemplateColumn(
        template_name="orga/tables/columns/timesince.html",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        initial_sort_descending=True,
    )
    pw_reset_time = TemplateColumn(
        template_name="orga/tables/columns/timesince.html",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        initial_sort_descending=True,
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
