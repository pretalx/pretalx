# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.signup import AttendeeSignupTable
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup

pytestmark = pytest.mark.unit


def test_attendee_signup_table_render_state_returns_localised_label():
    table = AttendeeSignupTable(data=AttendeeSignup.objects.none())

    rendered = table.render_state(AttendeeSignupStates.CONFIRMED, record=None)
    expected = dict(AttendeeSignupStates.choices)[AttendeeSignupStates.CONFIRMED]
    assert str(rendered) == str(expected)


def test_attendee_signup_table_render_state_returns_value_for_unknown():
    table = AttendeeSignupTable(data=AttendeeSignup.objects.none())
    assert table.render_state("not-a-state", record=None) == "not-a-state"
