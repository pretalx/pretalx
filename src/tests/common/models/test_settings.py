# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import uuid

import pytest

import pretalx.common.models.settings
from pretalx.common.models.settings import GlobalSettings

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_get_instance_identifier_creates_and_persists(monkeypatch):
    monkeypatch.setattr(pretalx.common.models.settings, "INSTANCE_IDENTIFIER", None)
    first = GlobalSettings().get_instance_identifier()

    monkeypatch.setattr(pretalx.common.models.settings, "INSTANCE_IDENTIFIER", None)
    second = GlobalSettings().get_instance_identifier()

    assert isinstance(first, uuid.UUID)
    assert first == second


def test_get_instance_identifier_uses_module_cache(monkeypatch):
    cached = uuid.uuid4()
    monkeypatch.setattr(pretalx.common.models.settings, "INSTANCE_IDENTIFIER", cached)

    assert GlobalSettings().get_instance_identifier() == cached
