import importlib
import json

import pytest
from django.conf import settings
from django.test import override_settings

from pretalx.common.templatetags import vite as vite_module
from pretalx.common.templatetags.vite import (
    generate_css_tags,
    generate_script_tag,
    vite_asset,
    vite_hmr,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def vite_manifest():
    """Save and restore the vite manifest dict for tests that modify it."""
    original = dict(vite_module._MANIFEST)
    yield vite_module._MANIFEST
    vite_module._MANIFEST.clear()
    vite_module._MANIFEST.update(original)


@override_settings(VITE_DEV_MODE=True, VITE_DEV_SERVER="http://localhost:5173")
def test_generate_script_tag_dev_mode():
    tag = generate_script_tag("src/main.js", {"type": "module"})
    assert '<script type="module"' in tag
    assert "localhost:5173" in tag
    assert "src/main.js" in tag


@override_settings(VITE_DEV_MODE=False, STATIC_URL="/static/")
def test_generate_script_tag_production_mode():
    tag = generate_script_tag("assets/main.abc.js", {"type": "module"})
    assert '<script type="module"' in tag
    assert "/static/assets/main.abc.js" in tag


def test_vite_asset_empty_path():
    assert vite_asset("") == ""


@override_settings(VITE_DEV_MODE=True, VITE_DEV_SERVER="http://localhost:5173")
def test_vite_asset_dev_mode():
    result = vite_asset("src/main.js")
    assert '<script type="module"' in result
    assert "localhost:5173" in result


@override_settings(VITE_DEV_MODE=False, STATIC_URL="/static/")
def test_vite_asset_production_mode(vite_manifest):
    vite_manifest["src/main.js"] = {
        "file": "assets/main.abc123.js",
        "css": ["assets/main.abc123.css"],
    }
    result = vite_asset("src/main.js")
    assert "assets/main.abc123.js" in result
    assert "assets/main.abc123.css" in result
    assert '<link rel="stylesheet"' in result


@override_settings(VITE_DEV_MODE=False)
def test_vite_asset_production_missing_entry_raises(vite_manifest):
    vite_manifest.clear()
    with pytest.raises(RuntimeError, match="Cannot find"):
        vite_asset("nonexistent.js")


@override_settings(VITE_DEV_MODE=True, VITE_DEV_SERVER="http://localhost:5173")
def test_vite_hmr_dev_mode():
    result = vite_hmr()
    assert "@vite/client" in result
    assert '<script type="module"' in result


@override_settings(VITE_DEV_MODE=False)
def test_vite_hmr_production_returns_empty():
    assert vite_hmr() == ""


@override_settings(VITE_DEV_MODE=False, STATIC_URL="/static/")
def test_generate_css_tags_with_imports(vite_manifest):
    """CSS tags include imported dependencies recursively."""
    vite_manifest.update(
        {
            "src/main.js": {
                "file": "assets/main.js",
                "css": ["assets/main.css"],
                "imports": ["src/vendor.js"],
            },
            "src/vendor.js": {"file": "assets/vendor.js", "css": ["assets/vendor.css"]},
        }
    )
    tags = generate_css_tags("src/main.js")
    css_text = "".join(tags)
    assert "assets/main.css" in css_text
    assert "assets/vendor.css" in css_text


@override_settings(VITE_DEV_MODE=False, STATIC_URL="/static/")
def test_generate_css_tags_no_css_key(vite_manifest):
    """Manifest entry without a 'css' key produces no link tags."""
    vite_manifest["src/util.js"] = {"file": "assets/util.js"}
    tags = generate_css_tags("src/util.js")
    assert tags == []


@override_settings(VITE_DEV_MODE=False, STATIC_URL="/static/")
def test_generate_css_tags_deduplicates(vite_manifest):
    """Same CSS file imported via multiple paths is only included once."""
    vite_manifest.update(
        {
            "src/main.js": {
                "file": "assets/main.js",
                "css": ["assets/shared.css"],
                "imports": ["src/vendor.js"],
            },
            "src/vendor.js": {"file": "assets/vendor.js", "css": ["assets/shared.css"]},
        }
    )
    tags = generate_css_tags("src/main.js")
    css_text = "".join(tags)
    assert css_text.count("assets/shared.css") == 1


@override_settings(VITE_DEV_MODE=False, VITE_IGNORE=False)
def test_vite_manifest_loaded_on_import(vite_manifest):
    """When VITE_DEV_MODE is False, the manifest is read from disk at import time."""
    manifest_path = settings.STATIC_ROOT / "pretalx-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_data = {"src/app.js": {"file": "assets/app.123.js"}}
    manifest_path.write_text(json.dumps(manifest_data))
    try:
        importlib.reload(vite_module)
        assert manifest_data == vite_module._MANIFEST
    finally:
        manifest_path.unlink(missing_ok=True)
        importlib.reload(vite_module)


@override_settings(VITE_DEV_MODE=False, VITE_IGNORE=False)
def test_vite_manifest_missing_file_logs_warning(vite_manifest):
    """When the manifest file doesn't exist, a warning is logged."""
    manifest_path = settings.STATIC_ROOT / "pretalx-manifest.json"
    manifest_path.unlink(missing_ok=True)
    try:
        importlib.reload(vite_module)
        assert vite_module._MANIFEST == {}
    finally:
        importlib.reload(vite_module)
