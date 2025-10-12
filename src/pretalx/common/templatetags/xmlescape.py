# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

from xml.sax.saxutils import escape

import django.utils.safestring
from django import template

register = template.Library()
strip_ascii = dict.fromkeys(list(range(9)) + list(range(11, 32)))


@register.filter
def xmlescape(text):
    text = str(text)  # resolve lazy i18n string
    text = text.translate(strip_ascii)  # remove ascii control characters
    text = escape(text)  # escape ><&
    text = text.encode(
        "ascii", "xmlcharrefreplace"
    ).decode()  # convert all non-ascii to &#xxx;
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return django.utils.safestring.mark_safe(text)
