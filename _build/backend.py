# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""
This build backend is a very thin setuptools wrapper to compile our
frontend into the wheel, so that installing from wheels needs no
npm/node. The compiled asset is shipped and then picked up by
``rebuild``/``collectstatic`` in the installed package.

Editable/source installs/sdists skip this and build the frontend via
npm when ``rebuild`` is run.
"""

import sys
from pathlib import Path

from setuptools import build_meta as _orig
from setuptools.build_meta import *  # noqa: F401,F403

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from pretalx._build import build_assets

    build_assets()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)
