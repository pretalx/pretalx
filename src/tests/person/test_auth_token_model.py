# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.models import UserApiToken
from pretalx.person.models.auth_token import (
    ENDPOINTS,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
)


@pytest.mark.parametrize(
    ("endpoints", "expected_preset"),
    (
        ({ep: list(READ_PERMISSIONS) for ep in ENDPOINTS}, "read"),
        ({ep: list(WRITE_PERMISSIONS) for ep in ENDPOINTS}, "write"),
        ({}, "custom"),
        ({"events": ["list", "retrieve"], "submissions": ["list"]}, "custom"),
        ({ep: list(READ_PERMISSIONS) for ep in list(ENDPOINTS)[:-1]}, "custom"),
    ),
    ids=["read_all", "write_all", "empty", "partial", "missing_endpoint"],
)
def test_permission_preset(endpoints, expected_preset):
    token = UserApiToken(endpoints=endpoints)
    assert token.permission_preset == expected_preset


@pytest.mark.parametrize(
    ("endpoints", "expected"),
    (
        ({}, []),
        (
            {"events": ["list", "retrieve"]},
            [("/events", ["Read list", "Read details"])],
        ),
        (
            {"events": ["list"], "submissions": ["create", "update"]},
            [("/events", ["Read list"]), ("/submissions", ["Create", "Update"])],
        ),
    ),
    ids=["empty", "single_endpoint", "multiple_endpoints"],
)
def test_get_endpoint_permissions_display(endpoints, expected):
    token = UserApiToken(endpoints=endpoints)
    assert token.get_endpoint_permissions_display() == expected
