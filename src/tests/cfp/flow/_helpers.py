# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
"""Shared helpers for cfp.flow tests."""

from types import SimpleNamespace

from tests.utils import SimpleSession


def make_cfp_session(tmpid="abc123", data=None, initial=None, files=None, **extra):
    """Build a session dict with a ready-to-use cfp sub-dict."""
    entry = {"data": data or {}, "initial": initial or {}, "files": files or {}}
    entry.update(extra)
    return SimpleSession({"cfp": {tmpid: entry}})


def make_resolver(tmpid="abc123", **kwargs):
    """Build a minimal resolver_match for CfP step unit tests."""
    return SimpleNamespace(kwargs={"tmpid": tmpid, **kwargs})
