import math
from datetime import timedelta

import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretalx.submission.models import SubmitterAccessCode
from tests.factories import SubmitterAccessCodeFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_access_code_log_fields():
    code = SubmitterAccessCodeFactory()
    assert code.log_prefix == "pretalx.access_code"
    assert code.log_parent == code.event


@pytest.mark.django_db
def test_access_code_generates_code_on_create():
    code = SubmitterAccessCodeFactory()
    assert code.code
    assert len(code.code) == 32


@pytest.mark.parametrize(
    ("maximum_uses", "redeemed", "expected"),
    (
        (1, 0, True),
        (10, 5, True),
        (1, 1, False),
        (10, 10, False),
        (None, 0, True),
        (None, 100, True),
        (0, 0, True),
    ),
)
def test_access_code_redemptions_valid(maximum_uses, redeemed, expected):
    code = SubmitterAccessCode(maximum_uses=maximum_uses, redeemed=redeemed)
    assert code.redemptions_valid is expected


@pytest.mark.parametrize(
    ("maximum_uses", "redeemed", "expected"),
    (
        (0, 0, math.inf),
        (0, 10, math.inf),
        (None, 10, math.inf),
        (None, 0, math.inf),
        (10, 1, 9),
        (10, 10, 0),
        (1, 1, 0),
        (1, 0, 1),
    ),
)
def test_access_code_redemptions_left(maximum_uses, redeemed, expected):
    code = SubmitterAccessCode(maximum_uses=maximum_uses, redeemed=redeemed)
    assert code.redemptions_left == expected


@pytest.mark.parametrize(
    ("valid_until", "expected"),
    ((None, True), ("future", True), ("past", False)),
    ids=["no_deadline", "future_deadline", "past_deadline"],
)
def test_access_code_time_valid(valid_until, expected):
    if valid_until == "future":
        valid_until = now() + timedelta(days=1)
    elif valid_until == "past":
        valid_until = now() - timedelta(days=1)
    code = SubmitterAccessCode(valid_until=valid_until)
    assert code.time_valid is expected


@pytest.mark.parametrize(
    ("valid_until", "maximum_uses", "redeemed", "expected"),
    (
        (None, None, 0, True),
        (None, 1, 1, False),
        ("past", None, 0, False),
        ("past", 1, 1, False),
        ("future", 1, 0, True),
        ("future", 1, 1, False),
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
def test_access_code_is_valid(valid_until, maximum_uses, redeemed, expected):
    if valid_until == "past":
        valid_until = now() - timedelta(days=1)
    elif valid_until == "future":
        valid_until = now() + timedelta(days=1)
    code = SubmitterAccessCode(
        valid_until=valid_until, maximum_uses=maximum_uses, redeemed=redeemed
    )
    assert code.is_valid is expected


@pytest.mark.parametrize(
    ("to_input", "expected_recipients"),
    (
        ("test@example.com", [["test@example.com"]]),
        ("a@example.com,b@example.com", [["a@example.com"], ["b@example.com"]]),
        (["x@example.com", "y@example.com"], [["x@example.com"], ["y@example.com"]]),
    ),
    ids=["single_email", "comma_separated", "list"],
)
@pytest.mark.django_db
def test_access_code_send_invite(to_input, expected_recipients):
    code = SubmitterAccessCodeFactory()
    djmail.outbox = []

    code.send_invite(to_input, "Subject", "Body text")

    assert len(djmail.outbox) == len(expected_recipients)
    for mail, expected_to in zip(djmail.outbox, expected_recipients, strict=True):
        assert mail.to == expected_to
        assert mail.subject == "Subject"


@pytest.mark.django_db
def test_access_code_get_instance_data_includes_code():
    code = SubmitterAccessCodeFactory()
    data = code.get_instance_data()
    assert data["code"] == code.code
