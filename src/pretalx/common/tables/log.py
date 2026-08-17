# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.log import ACTION_TYPE_GROUPS, CONTENT_TYPE_NAMES
from pretalx.common.models import ActivityLog
from pretalx.common.tables.filters import ChoiceFilter, FilterChoice


class ObjectTypeFilter(ChoiceFilter):
    def get_choices(self):
        if not self.event:
            return []
        content_type_ids = (
            ActivityLog.objects.filter(event=self.event)
            .values_list("content_type", flat=True)
            .distinct()
        )
        choices = []
        for content_type in ContentType.objects.filter(id__in=content_type_ids):
            key = f"{content_type.app_label}.{content_type.model}"
            choices.append(
                FilterChoice(
                    value=str(content_type.id),
                    label=CONTENT_TYPE_NAMES.get(
                        key, f"{content_type.app_label} {content_type.model}"
                    ),
                )
            )
        return sorted(choices, key=lambda choice: str(choice.label))


class ActionTypeFilter(ChoiceFilter):
    def get_choices(self):
        if not self.event:
            return []
        present = set(
            ActivityLog.objects.filter(event=self.event)
            .values_list("action_type", flat=True)
            .distinct()
        )
        choices = []
        grouped = set()
        for group_name, actions in ACTION_TYPE_GROUPS.items():
            for action_type, label in actions:
                if action_type in present:
                    choices.append(
                        FilterChoice(
                            value=action_type, label=label, group=str(group_name)
                        )
                    )
                    grouped.add(action_type)
        other = pgettext_lazy("history filter category", "Other")
        choices.extend(
            FilterChoice(
                value=action_type,
                label=action_type.replace("pretalx.", "").replace(".", " ").title(),
                group=str(other),
            )
            for action_type in sorted(present - grouped)
        )
        return choices


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
