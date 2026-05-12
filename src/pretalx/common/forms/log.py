# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.log import ACTION_TYPE_GROUPS, CONTENT_TYPE_NAMES
from pretalx.common.models import ActivityLog


class LogFilterForm(forms.Form):
    object_type = forms.ChoiceField(
        required=False, label=_("Object type"), widget=forms.Select()
    )
    action_type = forms.ChoiceField(
        required=False, label=_("Action"), widget=forms.Select()
    )

    default_renderer = InlineFormRenderer

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

        if not event:
            return

        # Build object type choices from existing logs
        content_type_ids = (
            ActivityLog.objects.filter(event=event)
            .values_list("content_type", flat=True)
            .distinct()
        )
        content_types = ContentType.objects.filter(id__in=content_type_ids)

        object_type_choices = [("", _("All object types"))]
        for ct in content_types:
            key = f"{ct.app_label}.{ct.model}"
            name = CONTENT_TYPE_NAMES.get(key, f"{ct.app_label} {ct.model}")
            object_type_choices.append((ct.id, name))

        object_type_choices.sort(key=lambda x: str(x[1]))
        self.fields["object_type"].choices = object_type_choices

        # Build action type choices from existing logs
        action_types = (
            ActivityLog.objects.filter(event=event)
            .values_list("action_type", flat=True)
            .distinct()
            .order_by("action_type")
        )

        action_type_choices = [("", _("All action types"))]
        seen_actions = set()

        # Add grouped actions
        for group_name, actions in ACTION_TYPE_GROUPS.items():
            group_actions = []
            for action_type, label in actions:
                if action_type in action_types:
                    group_actions.append((action_type, label))
                    seen_actions.add(action_type)
            if group_actions:
                action_type_choices.append((str(group_name), group_actions))

        # Add ungrouped actions
        other_actions = []
        for action_type in action_types:
            if action_type not in seen_actions:
                display_name = (
                    action_type.replace("pretalx.", "").replace(".", " ").title()
                )
                other_actions.append((action_type, display_name))

        if other_actions:
            action_type_choices.append(
                (pgettext_lazy("history filter category", "Other"), other_actions)
            )

        self.fields["action_type"].choices = action_type_choices

    def filter_queryset(self, qs):
        """Apply filters to the queryset."""
        object_type = self.cleaned_data.get("object_type")
        if object_type:
            qs = qs.filter(content_type_id=object_type)

        action_type = self.cleaned_data.get("action_type")
        if action_type:
            qs = qs.filter(action_type=action_type)

        return qs

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}
