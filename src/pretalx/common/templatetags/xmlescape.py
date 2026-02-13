# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import django.utils.safestring
from django import template

from pretalx.common.text.xml import xmlescape as _xmlescape

register = template.Library()


@register.filter
def xmlescape(text):
    return django.utils.safestring.mark_safe(_xmlescape(text))
