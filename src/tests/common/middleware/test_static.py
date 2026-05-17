# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django.test import override_settings

from pretalx.common.middleware import PretalxWhiteNoiseMiddleware

pytestmark = pytest.mark.unit


def _build_middleware(tmp_path, manifest):
    if manifest is not None:
        (tmp_path / "pretalx-manifest.json").write_text(json.dumps(manifest))
    with override_settings(STATIC_ROOT=tmp_path, STATIC_URL="/static/"):
        return PretalxWhiteNoiseMiddleware(get_response=lambda request: request)


def test_vite_bundle_files_are_immutable(tmp_path):
    mw = _build_middleware(
        tmp_path,
        {"src/main.js": {"file": "main-AbC123.js", "css": ["main-AbC123.css"]}},
    )

    assert mw.vite_bundle == {"main-AbC123.js", "main-AbC123.css"}
    assert mw.immutable_file_test("/p", "/static/main-AbC123.js") is True
    assert mw.immutable_file_test("/p", "/static/main-AbC123.css") is True


def test_non_bundle_files_fall_back_to_default(tmp_path):
    mw = _build_middleware(tmp_path, {"src/main.js": {"file": "main-AbC123.js"}})

    # An unhashed, non-bundle static file must not be marked immutable...
    assert mw.immutable_file_test("/p", "/static/scripts/app.js") is False
    # ...and neither is anything outside the static prefix.
    assert mw.immutable_file_test("/p", "/media/uploads/file.js") is False


def test_missing_manifest_yields_no_immutable_bundle(tmp_path):
    mw = _build_middleware(tmp_path, None)

    assert mw.vite_bundle == set()
    assert mw.immutable_file_test("/p", "/static/main-AbC123.js") is False


def test_init_scans_static_root_without_autorefresh(tmp_path):
    """With autorefresh off (production), WhiteNoise scans STATIC_ROOT during
    __init__ and calls immutable_file_test for every file found, so
    vite_bundle must already exist at that point."""
    (tmp_path / "pretalx-manifest.json").write_text(
        json.dumps({"src/main.js": {"file": "main-AbC123.js"}})
    )
    (tmp_path / "main-AbC123.js").write_text("console.log(1)")

    with override_settings(
        STATIC_ROOT=tmp_path, STATIC_URL="/static/", WHITENOISE_AUTOREFRESH=False
    ):
        mw = PretalxWhiteNoiseMiddleware(get_response=lambda request: request)

    assert mw.vite_bundle == {"main-AbC123.js"}
    assert "/static/main-AbC123.js" in mw.files
    assert mw.immutable_file_test("/p", "/static/main-AbC123.js") is True
