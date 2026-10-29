# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import math
from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretalx.submission.models import SubmitterAccessCode
from tests.factories import SubmitterAccessCodeFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_access_code_generates_code_on_create():
    code = SubmitterAccessCodeFactory()

    assert len(code.code) == 32
    assert code.log_parent == code.event
    assert code.get_instance_data()["code"] == code.code


@pytest.mark.parametrize(
    ("maximum_uses", "redeemed", "valid", "left"),
    (
        (1, 0, True, 1),
        (10, 5, True, 5),
        (1, 1, False, 0),
        (10, 10, False, 0),
        (None, 0, True, math.inf),
        (None, 100, True, math.inf),
        (0, 0, True, math.inf),
        (0, 10, True, math.inf),
    ),
)
def test_access_code_redemptions(maximum_uses, redeemed, valid, left):
    code = SubmitterAccessCode(maximum_uses=maximum_uses, redeemed=redeemed)

    assert code.redemptions_valid is valid
    assert code.redemptions_left == left


@pytest.mark.parametrize(
    ("valid_until", "maximum_uses", "redeemed", "time_valid", "expected"),
    (
        (None, None, 0, True, True),
        (None, 1, 1, True, False),
        ("past", None, 0, False, False),
        ("past", 1, 1, False, False),
        ("future", 1, 0, True, True),
        ("future", 1, 1, True, False),
    ),
    ids=[
        "no_limits",
        "no_time_limit_but_redeemed",
        "expired_no_use_limit",
        "expired_and_redeemed",
        "valid_time_with_uses",
        "valid_time_but_redeemed",
    ],
)
def test_access_code_is_valid(
    valid_until, maximum_uses, redeemed, time_valid, expected
):
    match valid_until:
        case "past":
            valid_until = now() - timedelta(days=1)
        case "future":
            valid_until = now() + timedelta(days=1)
    code = SubmitterAccessCode(
        valid_until=valid_until, maximum_uses=maximum_uses, redeemed=redeemed
    )

    assert code.time_valid is time_valid
    assert code.is_valid is expected
