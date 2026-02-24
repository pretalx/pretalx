# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import gettext as gettext_module
import json
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import to_locale


def get_language_scores():
    localedir = settings.LOCALE_PATHS[0]
    pot = polib.pofile(str(localedir / "django.pot"))
    total = len(pot)
    percentages = {}

    for lang_code in settings.LANGUAGES_INFORMATION:
        if lang_code == "en":
            percentages[lang_code] = 100
            continue
        locale = to_locale(lang_code)
        mo_path = gettext_module.find("django", localedir=localedir, languages=[locale])
        if not mo_path:
            percentages[lang_code] = 0
            continue
        po = polib.pofile(str(Path(mo_path).with_suffix(".po")))
        percentages[lang_code] = round(len(po.translated_entries()) / total * 100)
    return percentages


class Command(BaseCommand):
    help = "Update translation percentages in the JSON file based on actual translation completeness"

    def handle(self, *args, **options):  # pragma: no cover -- pure file I/O
        updated_percentages = get_language_scores()
        json_path = settings.LOCALE_PATHS[0] / "translation_percentages.json"
        with json_path.open("w") as f:
            json.dump(updated_percentages, f, indent=2, sort_keys=True)
