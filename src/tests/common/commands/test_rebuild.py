# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import io

import pytest

from pretalx.common.management.commands.rebuild import Command

pytestmark = pytest.mark.unit


def test_compress_bundle_writes_gz_and_br_siblings(tmp_path):
    (tmp_path / "app-Abc123.js").write_text("console.log('hello world');\n" * 200)

    Command()._compress_bundle(tmp_path, {"app-Abc123.js"})

    assert (tmp_path / "app-Abc123.js.gz").exists()
    assert (tmp_path / "app-Abc123.js.br").exists()


def test_compress_bundle_skips_uncompressible_extensions(tmp_path):
    (tmp_path / "logo-Abc.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)

    Command()._compress_bundle(tmp_path, {"logo-Abc.png"})

    assert not (tmp_path / "logo-Abc.png.gz").exists()
    assert not (tmp_path / "logo-Abc.png.br").exists()


def test_compress_bundle_degrades_instead_of_aborting(tmp_path):
    # A directory where a file is expected makes the WhiteNoise Compressor
    # raise: the rebuild must continue and warn, not crash.
    (tmp_path / "weird-Abc.js").mkdir()
    buffer = io.StringIO()

    Command(stdout=buffer, no_color=True)._compress_bundle(tmp_path, {"weird-Abc.js"})

    assert "served uncompressed" in buffer.getvalue()
