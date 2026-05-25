# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.signup import AttendeeSignupTable
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (
            AttendeeSignupStates.CONFIRMED,
            str(dict(AttendeeSignupStates.choices)[AttendeeSignupStates.CONFIRMED]),
        ),
        ("not-a-state", "not-a-state"),
    ),
    ids=("known", "unknown"),
)
def test_attendee_signup_table_render_state(value, expected):
    table = AttendeeSignupTable(data=AttendeeSignup.objects.none())

    assert str(table.render_state(value)) == expected
