# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Jahongir
# SPDX-FileContributor: Laura Klünder

from copy import deepcopy

from django.utils.functional import Promise
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString

from pretalx.common.language import language


def cfp_session(request):
    request.session.modified = True
    if "cfp" not in request.session or not request.session["cfp"]:
        request.session["cfp"] = {}
    session_data = request.session["cfp"]
    key = request.resolver_match.kwargs["tmpid"]
    if key not in session_data:
        session_data[key] = {"data": {}, "initial": {}, "files": {}}
    return session_data[key]


def cfp_field_labels():
    """CfP-specific display labels for fields.

    These override the model verbose_name when displaying fields in the CfP editor.
    Only fields that need a different label than their model verbose_name are listed.
    """
    return {
        "title": _("Title"),
        "additional_speaker": _("Additional speakers"),
        "availabilities": _("Availability"),
        "resources": _("Resources"),
    }


def i18n_string(data, locales):
    """Normalize ``data`` to a :class:`LazyI18nString` covering ``locales``.

    Accepts a plain string, a dict, or a lazy/translatable string. Missing
    locale entries are filled by running the English source through
    ``gettext`` under each target locale, so values authored in English in the
    CfP editor automatically pick up existing translations.
    """
    if isinstance(data, LazyI18nString):
        return data
    data = deepcopy(data)
    with language("en"):
        if isinstance(data, Promise):
            data = str(data)
        if isinstance(data, str):
            data = {"en": str(data)}
        elif not isinstance(data, dict):
            data = {"en": ""}
        english = data.get("en", "")

    for locale in locales:
        if locale != "en" and not data.get(locale):
            with language(locale):
                data[locale] = gettext(english)
    return LazyI18nString(data)


def serialize_value(value):
    """JSON ``default=`` callable for form cleaned_data and similar.

    Returns the primary key for model instances, recurses into iterables,
    delegates to ``serialize()`` when available, and falls back to ``str()``.
    """
    if getattr(value, "pk", None):
        return value.pk
    if getattr(value, "__iter__", None):
        return [serialize_value(element) for element in value]
    if getattr(value, "serialize", None):
        return value.serialize()
    return str(value)
