# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template

register = template.Library()


@register.filter
def get_feature_flag(event, feature_flag: str):
    return event.get_feature_flag(feature_flag)
