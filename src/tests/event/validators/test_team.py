# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.event.validators.team import (
    TEAM_PERMISSION_FIELDS,
    validate_team_event_coverage,
    validate_team_has_permission,
)

pytestmark = pytest.mark.unit


def test_validate_team_event_coverage_accepts_all_events():
    validate_team_event_coverage(all_events=True, limit_events=[])


def test_validate_team_event_coverage_accepts_limit_events():
    validate_team_event_coverage(all_events=False, limit_events=[object()])


def test_validate_team_event_coverage_rejects_neither():
    with pytest.raises(ValidationError) as exc_info:
        validate_team_event_coverage(all_events=False, limit_events=[])
    assert "limit_events" in exc_info.value.message_dict


def test_validate_team_has_permission_accepts_any_set():
    for field in TEAM_PERMISSION_FIELDS:
        validate_team_has_permission({f: (f == field) for f in TEAM_PERMISSION_FIELDS})


def test_validate_team_has_permission_rejects_none():
    with pytest.raises(ValidationError):
        validate_team_has_permission(dict.fromkeys(TEAM_PERMISSION_FIELDS, False))


def test_validate_team_has_permission_ignores_unrelated_truthy_keys():
    with pytest.raises(ValidationError):
        validate_team_has_permission({"name": "team", "all_events": True})
