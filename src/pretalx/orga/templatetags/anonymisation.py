# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template

register = template.Library()


@register.filter
def anonymised_value(submission, attribute):
    return submission.get_anonymised(attribute)
