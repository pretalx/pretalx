# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from pretalx.common.log import action_type_label
from pretalx.common.models import ActivityLog
from pretalx.common.tables.filters import ChoiceFilter, FilterChoice


def content_type_label(content_type):
    model = content_type.model_class()
    if model is None:
        return content_type.name
    return capfirst(model._meta.verbose_name_plural)


class ObjectTypeFilter(ChoiceFilter):
    def get_choices(self):
        if not self.event:
            return []
        content_type_ids = (
            ActivityLog.objects.filter(event=self.event)
            .values_list("content_type", flat=True)
            .distinct()
        )
        choices = [
            FilterChoice(
                value=str(content_type.id), label=content_type_label(content_type)
            )
            for content_type in ContentType.objects.filter(id__in=content_type_ids)
        ]
        return sorted(choices, key=lambda choice: str(choice.label))


class ActionTypeFilter(ChoiceFilter):
    def get_primary_content_types(self):
        rows = (
            ActivityLog.objects.filter(event=self.event)
            .values("action_type", "content_type")
            .annotate(count=Count("pk"))
            .order_by()
        )
        primary = {}
        for row in sorted(
            rows,
            key=lambda row: (row["action_type"], -row["count"], row["content_type"]),
        ):
            primary.setdefault(row["action_type"], row["content_type"])
        return primary

    def get_choices(self):
        if not self.event:
            return []
        primary = self.get_primary_content_types()
        content_types = {
            content_type.pk: content_type
            for content_type in ContentType.objects.filter(pk__in=set(primary.values()))
        }
        choices = [
            FilterChoice(
                value=action_type,
                label=action_type_label(action_type),
                group=str(content_type_label(content_types[content_type_id])),
            )
            for action_type, content_type_id in primary.items()
        ]
        return sorted(choices, key=lambda choice: (choice.group, str(choice.label)))


def log_filters(context):
    return [
        ObjectTypeFilter(
            name="object_type",
            field="content_type_id",
            label=_("Object type"),
            empty_label=_("All object types"),
        ),
        ActionTypeFilter(
            name="action_type", label=_("Action"), empty_label=_("All action types")
        ),
    ]
