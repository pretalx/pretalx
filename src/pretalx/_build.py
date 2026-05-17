# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""
We compile the frontend during wheel build, so that installing pretalx
from PyPI wheels requires no npm/node.

The schedule editor is emitted into ``schedule-editor/dist`` that is
explicitly shipped in the wheel and then copied by ``rebuild`` into
``STATIC_ROOT``. The public schedule component is placed in the source
static dir where it is collected by ``collectstatic`` like any other
static file.

Called by ``_build/backend.py`` which calls ``build_assets``.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRONTEND_DIR = HERE / "frontend"
MANIFEST_DIST = FRONTEND_DIR / "schedule-editor" / "dist"
WIDGET_BUNDLE = HERE / "static" / "agenda" / "js" / "pretalx-schedule.min.js"

# Marker, written only here and never by runtime ``rebuild``. Indicates to
# ``rebuild`` that we are in a wheel install with prebuilt static assets.
# Placed insite MANIFEST_DIST so that a source-side rebuild would wipe it.
PREBUILT_MARKER = MANIFEST_DIST / ".prebuilt"


def bundle_filenames(manifest_path):
    """Names of every file emitted by the Vite build, per its manifest.

    These are content-hashed by Vite and shipped outside Django's
    staticfiles manifest, so both ``rebuild`` (to prune old versions) and
    the WhiteNoise middleware (to mark them immutable) need to know them.
    """
    files = set()
    try:
        manifest = json.loads(Path(manifest_path).read_text())
    except (OSError, json.JSONDecodeError):
        return files
    for entry in manifest.values():
        if file := entry.get("file"):
            files.add(file)
        files.update(entry.get("css", []))
        files.update(entry.get("assets", []))
    return files


def build_assets():
    if not shutil.which("npm"):
        raise RuntimeError(
            "npm was not found, but is required to build the pretalx frontend "
            "from source. Install Node.js/npm and try again, or install a"
            "wheel from PyPI, which includes the built frontend."
        )

    env = os.environ.copy()
    env["OUT_DIR"] = str(MANIFEST_DIST)
    env["BASE_URL"] = "./"

    # vite builds with ``emptyOutDir: false`` (because the manifest and
    # widget builds share output dirs), so a stale ``dist/`` from a previous
    # build would leave orphan chunks in the wheel and let the existence
    # check pass even on an unsuccessful build.
    shutil.rmtree(MANIFEST_DIST, ignore_errors=True)
    for stale in WIDGET_BUNDLE.parent.glob(WIDGET_BUNDLE.name + "*"):
        stale.unlink()

    subprocess.check_call(["npm", "ci"], cwd=FRONTEND_DIR)  # noqa: S607 -- npm location may be nonstandard
    subprocess.check_call(["npm", "run", "build"], cwd=FRONTEND_DIR, env=env)  # noqa: S607 -- npm location may be nonstandard

    # A wheel without the frontend is silently broken at runtime so we fail loudly.
    manifest = MANIFEST_DIST / "pretalx-manifest.json"
    for artifact in (manifest, WIDGET_BUNDLE):
        if not artifact.exists():
            raise RuntimeError(
                f"Frontend build did not produce {artifact}; refusing to "
                "build a package without the frontend."
            )

    PREBUILT_MARKER.write_text(
        "This frontend was prebuilt during the pretalx package build and is "
        "shipped in the wheel. `pretalx rebuild` uses it as-is and does not "
        "need npm/node. Building from source removes this marker.\n"
    )
