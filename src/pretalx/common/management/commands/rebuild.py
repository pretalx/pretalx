# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import os
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.core.management.base import BaseCommand
from django.test import override_settings
from whitenoise.compress import Compressor

from pretalx._build import MANIFEST_DIST, PREBUILT_MARKER, bundle_filenames
from pretalx.common.models.settings import GlobalSettings


class Command(BaseCommand):
    help = "Rebuild static files and language files"

    def add_arguments(self, parser):
        parser.add_argument(
            "-c",
            "--clear",
            action="store_true",
            dest="clear",
            help="Clear the existing files using the storage before trying to copy or link the original file.",
        )
        parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            dest="silent",
            help="Silence most of the build output.",
        )
        parser.add_argument(
            "--npm-install",
            action="store_true",
            dest="npm_install",
            help="Update npm dependencies before building.",
        )

    def handle(self, *args, **options):
        silent = 0 if options.get("silent") else 1
        try:
            # There are broken translations (completely wrong brace format)
            # inside Sphinx that do not appear to get fixed. We ignore those,
            # and if other translations fail as well, we still try to continue.
            call_command("compilemessages", verbosity=silent, ignore=["*sphinx*"])
        except CommandError as e:
            self.stdout.write(
                self.style.ERROR(
                    "Failed to build translation files, proceeding regardless. "
                    f"Run `compilemessages` directly for full error message: {e}"
                )
            )

        # We check the PREBUILT_MARKER file to see if assets exist already
        # and were shipped via a wheel. If not, or if forced via ``--npm-install``,
        # we build from source.
        if PREBUILT_MARKER.exists() and not options["npm_install"]:
            self.stdout.write(
                "Using the prebuilt frontend shipped with the package; "
                "skipping the npm build. Pass --npm-install to rebuild it "
                "from source."
            )
        elif shutil.which("npm"):
            self._build_frontend(npm_install=options["npm_install"])
        else:
            self.stdout.write(
                self.style.WARNING(
                    "npm not found and no prebuilt frontend is present, so "
                    "the frontend cannot be built from source. Install npm, "
                    "or install a pretalx wheel from PyPI."
                )
            )

        call_command(
            "collectstatic", verbosity=silent, interactive=False, clear=options["clear"]
        )

        # We install the manifest bundle after ``collectstatic`` has
        # run because the ``--clear`` option would delete it.
        self._install_manifest_bundle()

        # This fails if we don't have db access, which is fine
        with suppress(Exception):
            gs = GlobalSettings()
            del gs.settings.update_check_last
            del gs.settings.update_check_result
            del gs.settings.update_check_result_warning

    def _build_frontend(self, *, npm_install):
        # ``npm run build`` produces the manifest bundle for same-origin
        # apps (schedule editor, public schedule) and the web component
        # for the embeddable schedule widget.
        frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
        # We build in a sibling dir and swap over after a successful build
        # so that a failed build leaves the previous working bundle in place.
        build_dir = MANIFEST_DIST.parent / ".dist.build"
        shutil.rmtree(build_dir, ignore_errors=True)
        env = os.environ.copy()
        env["OUT_DIR"] = str(build_dir)
        env["BASE_URL"] = settings.STATIC_URL
        try:
            with override_settings(VITE_IGNORE=True):
                if npm_install or not (frontend_dir / "node_modules").exists():
                    subprocess.check_call(["npm", "ci"], cwd=frontend_dir)  # noqa: S607 -- npm is commonly installed in user paths
                subprocess.check_call(
                    ["npm", "run", "build"],  # noqa: S607 -- npm is commonly installed in user paths
                    cwd=frontend_dir,
                    env=env,
                )
        except BaseException:
            shutil.rmtree(build_dir, ignore_errors=True)
            raise
        shutil.rmtree(MANIFEST_DIST, ignore_errors=True)
        build_dir.replace(MANIFEST_DIST)

    def _manifest_artifacts(self, manifest_path):
        return {manifest_path.name} | bundle_filenames(manifest_path)

    def _compress_bundle(self, target, names):
        # WhiteNoise precompresses all other staticfiles via its backend
        # (called by collectstatic). But as WhiteNoise does not know about
        # our injected files, we do the same here.
        try:
            compressor = Compressor(quiet=True)
            for name in names:
                path = target / name
                if path.exists() and compressor.should_compress(name):
                    compressor.compress(str(path))
        except Exception as e:  # noqa: BLE001 -- optional optimisation, see below
            # Compressor is a WhiteNoise-internal API. If a future
            # version changes it, degrade to serving the bundle
            # uncompressed.
            self.stdout.write(
                self.style.WARNING(
                    f"Could not precompress the frontend bundle ({e}); "
                    "it will be served uncompressed."
                )
            )

    def _install_manifest_bundle(self):
        if not (MANIFEST_DIST / "pretalx-manifest.json").exists():
            raise CommandError(
                f"The prebuilt frontend bundle is missing ({MANIFEST_DIST}). "
                "Installed wheels ship it; from a source checkout, install "
                "npm so `rebuild` can build the frontend."
            )
        target = Path(settings.STATIC_ROOT)
        target.mkdir(parents=True, exist_ok=True)
        # The hashed filenames change between versions and are not managed by
        # collectstatic, so we remove the previously installed bundle (via the
        # old manifest) before copying, if they exist.
        old_manifest = target / "pretalx-manifest.json"
        if old_manifest.exists():
            for name in self._manifest_artifacts(old_manifest):
                for path in (
                    target / name,
                    target / f"{name}.gz",
                    target / f"{name}.br",
                ):
                    with suppress(FileNotFoundError):
                        path.unlink()
        shutil.copytree(MANIFEST_DIST, target, dirs_exist_ok=True)
        self._compress_bundle(
            target, bundle_filenames(MANIFEST_DIST / "pretalx-manifest.json")
        )
