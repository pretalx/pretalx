# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from datetime import date

import pytest
from django.utils import translation
from i18nfield.strings import LazyI18nString

from pretalx.common.text.daterange import daterange
from pretalx.common.text.path import safe_filename
from pretalx.common.text.serialize import I18nStrJSONEncoder


@pytest.mark.parametrize(
    ("locale", "start", "end", "result"),
    (
        ("de", date(2003, 2, 1), date(2003, 2, 1), "1. Februar 2003"),
        ("en", date(2003, 2, 1), date(2003, 2, 1), "Feb. 1, 2003"),
        ("es", date(2003, 2, 1), date(2003, 2, 1), "1 de febrero de 2003"),
        ("de", date(2003, 2, 1), date(2003, 2, 3), "1.–3. Februar 2003"),
        ("en", date(2003, 2, 1), date(2003, 2, 3), "Feb. 1 – 3, 2003"),
        ("es", date(2003, 2, 1), date(2003, 2, 3), "1 - 3 de febrero de 2003"),
        ("de", date(2003, 2, 1), date(2003, 4, 3), "1. Februar – 3. April 2003"),
        ("en", date(2003, 2, 1), date(2003, 4, 3), "Feb. 1 – April 3, 2003"),
        ("es", date(2003, 2, 1), date(2003, 4, 3), "1 de febrero - 3 de abril de 2003"),
        ("de", date(2003, 2, 1), date(2005, 4, 3), "1. Februar 2003 – 3. April 2005"),
        ("en", date(2003, 2, 1), date(2005, 4, 3), "Feb. 1, 2003 – April 3, 2005"),
        (
            "es",
            date(2003, 2, 1),
            date(2005, 4, 3),
            "1 de febrero de 2003 -3 de abril de 2005",
        ),
    ),
)
def test_daterange(locale, start, end, result):
    with translation.override(locale):
        assert daterange(start, end) == result


@pytest.mark.parametrize(
    ("original_name", "target_name", "upload_dir", "expected"),
    (
        ("foo.bar", "avatar", None, "avatar_aaaaaaa.bar"),
        ("foo.bar", "logo", "event/img/", "event/img/logo_aaaaaaa.bar"),
        (
            "user_file.png",
            "image",
            "submissions/ABC/",
            "submissions/ABC/image_aaaaaaa.png",
        ),
        ("foo.bar", "foo", None, "foo_aaaaaaa.bar"),
        ("foo_.bar", "foo_", None, "foo__aaaaaaa.bar"),
        ("foo", "foo", None, "foo_aaaaaaa"),
        (
            "document.pdf",
            "document",
            "event/resources/",
            "event/resources/document_aaaaaaa.pdf",
        ),
        # Paths in filename are stripped (use upload_dir instead)
        ("/home/foo.bar", "avatar", None, "avatar_aaaaaaa.bar"),
        ("home/foo.bar", "foo", None, "foo_aaaaaaa.bar"),
        ("/absolute/path/doc.pdf", "doc", "resources/", "resources/doc_aaaaaaa.pdf"),
    ),
)
def test_hashed_path(original_name, target_name, upload_dir, expected, monkeypatch):
    monkeypatch.setattr(
        "pretalx.common.text.path.get_random_string", lambda x: "aaaaaaa"
    )
    from pretalx.common.text.path import hashed_path  # noqa: PLC0415

    assert (
        hashed_path(original_name, target_name=target_name, upload_dir=upload_dir)
        == expected
    )


@pytest.mark.parametrize(
    ("filename", "expected"), (("ö", "o"), ("å", "a"), ("ø", ""), ("α", ""))
)
def test_safe_filename(filename, expected):
    assert safe_filename(filename) == expected


@pytest.mark.django_db
def test_json_encoder_inheritance(event):
    assert I18nStrJSONEncoder().default(event) == {"id": event.pk, "type": "Event"}


@pytest.mark.django_db
def test_json_encoder_i18nstr(event):
    assert (
        I18nStrJSONEncoder().default(LazyI18nString({"en": "foo", "de": "bar"}))
        == "foo"
    )
