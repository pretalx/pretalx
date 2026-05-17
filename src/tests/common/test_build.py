# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest

from pretalx._build import bundle_filenames

pytestmark = pytest.mark.unit


def test_bundle_filenames_collects_file_css_and_assets(tmp_path):
    manifest = tmp_path / "pretalx-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "src/main.js": {
                    "file": "main-AbC123.js",
                    "css": ["main-AbC123.css"],
                    "assets": ["logo-Xy9.svg"],
                },
                "src/admin.js": {"file": "admin-Def456.js"},
                "src/_shared.js": {},
            }
        )
    )

    assert bundle_filenames(manifest) == {
        "main-AbC123.js",
        "main-AbC123.css",
        "logo-Xy9.svg",
        "admin-Def456.js",
    }


def test_bundle_filenames_missing_file_returns_empty(tmp_path):
    assert bundle_filenames(tmp_path / "does-not-exist.json") == set()


def test_bundle_filenames_invalid_json_returns_empty(tmp_path):
    manifest = tmp_path / "pretalx-manifest.json"
    manifest.write_text("{ not valid json")

    assert bundle_filenames(manifest) == set()
