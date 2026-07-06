# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.common.validators import validate_event_scope_coverage

pytestmark = pytest.mark.unit


def test_validate_event_scope_coverage_accepts_all_events():
    validate_event_scope_coverage(all_events=True, limit_events=[])


def test_validate_event_scope_coverage_accepts_limit_events():
    validate_event_scope_coverage(all_events=False, limit_events=[object()])


def test_validate_event_scope_coverage_rejects_neither():
    with pytest.raises(ValidationError) as exc_info:
        validate_event_scope_coverage(all_events=False, limit_events=[])
    assert "limit_events" in exc_info.value.message_dict
