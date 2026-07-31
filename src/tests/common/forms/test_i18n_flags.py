# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re
from pathlib import Path

import pytest
from django.conf import settings

import pretalx
from pretalx.common.language import LANGUAGE_NAMES

pytestmark = pytest.mark.unit

STATIC_DIR = Path(pretalx.__file__).parent / "static"
FLAG_DIR = STATIC_DIR / "vendored" / "flags"
STYLESHEET = STATIC_DIR / "orga" / "css" / "forms" / "i18n.css"

RULE_REGEX = re.compile(
    r'div\[lang="(?P<locale>[^"]+)"\][^{]*\{\s*'
    r'background-image: url\("/static/vendored/flags/(?P<flag>[^"]+)\.png"\);'
)

CONTENT_LOCALE_FLAGS = {
    "af": "za",
    "ar": "arab-league",
    "ar-dz": "dz",
    "az": "az",
    "be": "by",
    "bg": "bg",
    "bn": "bd",
    "bs": "ba",
    "cs": "cz",
    "da": "dk",
    "de": "de",
    "de-formal": "de",
    "el": "gr",
    "en": "gb",
    "en-au": "au",
    "en-gb": "gb",
    "es": "es",
    "es-ar": "ar",
    "es-co": "co",
    "es-mx": "mx",
    "es-ni": "ni",
    "es-ve": "ve",
    "et": "ee",
    "fa": "ir",
    "fi": "fi",
    "fr": "fr",
    "ga": "ie",
    "he": "il",
    "hi": "in",
    "hr": "hr",
    "ht": "ht",
    "hu": "hu",
    "hy": "am",
    "id": "id",
    "ig": "ng",
    "is": "is",
    "it": "it",
    "ja": "jp",
    "ja-jp": "jp",
    "ka": "ge",
    "kk": "kz",
    "km": "kh",
    "kn": "in",
    "ko": "kr",
    "ky": "kg",
    "lb": "lu",
    "lt": "lt",
    "lv": "lv",
    "mk": "mk",
    "ml": "in",
    "mn": "mn",
    "mr": "in",
    "ms": "my",
    "my": "mm",
    "nb": "no",
    "ne": "np",
    "nl": "nl",
    "nn": "no",
    "pa": "in",
    "pl": "pl",
    "pt": "pt",
    "pt-br": "br",
    "pt-pt": "pt",
    "ro": "ro",
    "ru": "ru",
    "sk": "sk",
    "sl": "si",
    "sq": "al",
    "sr": "rs",
    "sr-latn": "rs",
    "sv": "se",
    "sw": "tz",
    "ta": "in",
    "te": "in",
    "tg": "tj",
    "th": "th",
    "tk": "tm",
    "tr": "tr",
    "uk": "ua",
    "ur": "pk",
    "uz": "uz",
    "vi": "vn",
    "zh-hans": "cn",
    "zh-hant": "tw",
}

FLAGLESS_CONTENT_LOCALES = {
    "ast",
    "br",
    "ca",
    "ckb",
    "cy",
    "dsb",
    "eo",
    "eu",
    "fy",
    "gd",
    "gl",
    "hsb",
    "ia",
    "io",
    "kab",
    "os",
    "tt",
    "udm",
    "ug",
}


def parse_stylesheet():
    return {
        match.group("locale"): match.group("flag")
        for match in RULE_REGEX.finditer(STYLESHEET.read_text())
    }


def test_i18n_stylesheet_maps_content_locales_to_expected_flags():
    assert parse_stylesheet() == CONTENT_LOCALE_FLAGS


def test_i18n_flag_table_covers_all_known_content_locales():
    unknowable_locales = {"testlocale"} | {
        information["code"]
        for information in settings.LANGUAGES_INFORMATION.values()
        if "visible" in information
    }
    locales = set(LANGUAGE_NAMES) - unknowable_locales

    assert locales - set(CONTENT_LOCALE_FLAGS) - FLAGLESS_CONTENT_LOCALES == set()


def test_i18n_stylesheet_only_references_existing_flags():
    rules = parse_stylesheet()

    missing = {
        flag
        for flag in set(rules.values())
        if not (FLAG_DIR / f"{flag}.png").exists()
        or not (FLAG_DIR / f"{flag}.png.license").exists()
    }

    assert missing == set()


def test_i18n_stylesheet_rules_apply_to_all_i18n_elements():
    stylesheet = STYLESHEET.read_text()
    rules = parse_stylesheet()

    incomplete = {
        locale
        for locale in rules
        if f'div[lang="{locale}"],\ninput[lang="{locale}"],\ntextarea[lang="{locale}"] {{'
        not in stylesheet
    }

    assert incomplete == set()
