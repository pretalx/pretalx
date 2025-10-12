# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re

from django.conf import settings
from django.db import connection
from django.db.models.lookups import Transform
from django.utils import translation
from django.utils.formats import get_format

date_conversion_to_moment = {
    "%a": "ddd",
    "%A": "dddd",
    "%w": "d",
    "%d": "DD",
    "%b": "MMM",
    "%B": "MMMM",
    "%m": "MM",
    "%y": "YY",
    "%Y": "YYYY",
    "%H": "HH",
    "%I": "hh",
    "%p": "a",
    "%M": "mm",
    "%S": "ss",
    "%f": "SSSSSS",
    "%z": "ZZ",
    "%Z": "zz",
    "%j": "DDDD",
    "%U": "ww",  # fuzzy translation
    "%W": "WW",
    "%c": "",
    "%x": "",
    "%X": "",
}

moment_locales = {
    "af",
    "az",
    "bs",
    "de-at",
    "en-gb",
    "et",
    "fr-ch",
    "hi",
    "it",
    "ko",
    "me",
    "ms-my",
    "pa-in",
    "se",
    "sr",
    "th",
    "tzm-latn",
    "zh-hk",
    "ar",
    "be",
    "ca",
    "de",
    "en-ie",
    "eu",
    "fr",
    "hr",
    "ja",
    "ky",
    "mi",
    "my",
    "pl",
    "si",
    "ss",
    "tlh",
    "uk",
    "zh-tw",
    "ar-ly",
    "bg",
    "cs",
    "dv",
    "en-nz",
    "fa",
    "fy",
    "hu",
    "jv",
    "lb",
    "mk",
    "nb",
    "pt-br",
    "sk",
    "sv",
    "tl-ph",
    "uz",
    "ar-ma",
    "bn",
    "cv",
    "el",
    "eo",
    "fi",
    "gd",
    "hy-am",
    "ka",
    "lo",
    "ml",
    "ne",
    "pt",
    "sl",
    "sw",
    "tr",
    "vi",
    "ar-sa",
    "bo",
    "cy",
    "en-au",
    "es-do",
    "fo",
    "gl",
    "id",
    "kk",
    "lt",
    "mr",
    "nl",
    "ro",
    "sq",
    "ta",
    "tzl",
    "x-pseudo",
    "ar-tn",
    "br",
    "da",
    "en-ca",
    "es",
    "fr-ca",
    "he",
    "is",
    "km",
    "lv",
    "ms",
    "nn",
    "ru",
    "sr-cyrl",
    "te",
    "tzm",
    "zh-cn",
}

JS_REGEX = re.compile(r"(?<!\w)(" + "|".join(date_conversion_to_moment.keys()) + r")\b")


def get_javascript_format(format_name):
    format_value = get_format(format_name)[0]
    return JS_REGEX.sub(
        lambda regex: date_conversion_to_moment[regex.group()], format_value
    )


def get_moment_locale(locale=None):
    cur_lang = locale or translation.get_language()
    if cur_lang in moment_locales:
        return cur_lang
    if "-" in cur_lang or "_" in cur_lang:
        main = cur_lang.replace("_", "-").split("-")[0]
        if main in moment_locales:
            return main
    return settings.LANGUAGE_CODE


class Translate(Transform):
    name = "translate"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if connection.vendor == "postgresql":
            self.base_template = (
                "CASE "
                "WHEN %(expressions)s IS JSON OBJECT THEN "
                "COALESCE("
                "NULLIF(%(expressions)s::json->>'{locale}', ''), "
                "%(expressions)s::json->>'en',"
                "(SELECT value FROM json_each_text(%(expressions)s::json) LIMIT 1)"
                ")"
                "ELSE %(expressions)s::text "
                "END"
            )
        elif connection.vendor == "sqlite":
            self.base_template = (
                "CASE "
                "WHEN json_valid(%(expressions)s) THEN "
                "COALESCE("
                "NULLIF(json_extract(%(expressions)s, '$.{locale}'), ''), "
                "json_extract(%(expressions)s, '$.en'), "
                "(SELECT value FROM json_each(%(expressions)s) WHERE json_each.type != 'object' LIMIT 1)"
                ")"
                "ELSE %(expressions)s "
                "END"
            )
        else:
            raise NotImplementedError(
                f"Translate not supported for {connection.vendor}"
            )

    @property
    def template(self):
        # Lazy template eval in order to get the actual current language
        current_locale = translation.get_language()
        return self.base_template.format(locale=current_locale)
