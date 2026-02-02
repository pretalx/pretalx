# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import unicodedata
from pathlib import Path

from django.conf import settings
from django.utils.crypto import get_random_string


def hashed_path(original_name, target_name, upload_dir=None, max_length=100):
    """Generate upload path with hash for uniqueness.

    Args:
        original_name: Original filename (used only for extension extraction)
        target_name: Base name for the generated file (required)
        upload_dir: Directory path prefix
        max_length: Maximum total path length

    Returns:
        Path like "{upload_dir}/{target_name}_{random}.{ext}"
    """
    upload_dir = upload_dir or ""
    file_path = Path(original_name)
    file_ext = file_path.suffix
    random = get_random_string(7)

    file_root = target_name

    result = str(Path(upload_dir) / f"{file_root}_{random}{file_ext}")

    if max_length:
        full_path = str(Path(settings.MEDIA_ROOT) / result)
        if len(full_path) > max_length:
            excess = len(full_path) - max_length
            if len(file_root) > excess:
                file_root = file_root[:-excess]
                result = str(Path(upload_dir) / f"{file_root}_{random}{file_ext}")

    return result


def safe_filename(filename):
    return unicodedata.normalize("NFD", filename).encode("ASCII", "ignore").decode()
