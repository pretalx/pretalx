# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pathlib import PurePosixPath

from django.conf import settings
from whitenoise.middleware import WhiteNoiseMiddleware

from pretalx._build import bundle_filenames


class PretalxWhiteNoiseMiddleware(WhiteNoiseMiddleware):
    """
    WhiteNoise serves all static files that it finds in ``STATIC_ROOT``,
    but it only runs compression and adds cache-forever headers on
    files it *knows*, which excludes our manually-added Vite bundle.
    But since we do apply content hashing, we inject them here.
    """

    def __init__(self, *args, **kwargs):
        manifest = settings.STATIC_ROOT / "pretalx-manifest.json"
        self.vite_bundle = {
            PurePosixPath(name).name for name in bundle_filenames(manifest)
        }
        super().__init__(*args, **kwargs)

    def immutable_file_test(self, path, url):
        if PurePosixPath(url).name in self.vite_bundle:
            return True
        return super().immutable_file_test(path, url)
