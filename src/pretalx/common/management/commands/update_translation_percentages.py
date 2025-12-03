# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import gettext as gettext_module
import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import to_locale


def get_language_score(locale):
    catalog = {}
    localedir = settings.LOCALE_PATHS[0]

    try:
        translation = gettext_module.translation(
            domain="django",
            localedir=localedir,
            languages=[to_locale(locale)],
            fallback=False,
        )
    except Exception:
        return 1
    catalog.update(translation._catalog.copy())

    while translation._fallback:
        if not locale.startswith(translation._fallback.info().get("language", "XX")):
            break
        translation = translation._fallback
        catalog.update(translation._catalog.copy())

    if not catalog:
        return 1
    source_strings = [k[1] if isinstance(k, tuple) else k for k in catalog.keys()]
    return len(set(source_strings)) or 1


def get_language_scores():
    base_score = get_language_score("de")
    percentages = {}

    for lang_code in settings.LANGUAGES_INFORMATION.keys():
        if lang_code in ("en", "de"):
            percentages[lang_code] = 100
        else:
            lang_score = get_language_score(lang_code)
            percentage = round(lang_score / base_score * 100)
            percentages[lang_code] = percentage
    return percentages


class Command(BaseCommand):
    help = "Update translation percentages in the JSON file based on actual translation completeness"

    def handle(self, *args, **options):

        updated_percentages = get_language_scores()
        json_path = settings.LOCALE_PATHS[0] / "translation_percentages.json"
        with open(json_path, "w") as f:
            json.dump(updated_percentages, f, indent=2, sort_keys=True)
