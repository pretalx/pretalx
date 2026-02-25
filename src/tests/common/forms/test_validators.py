import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.utils.timezone import make_aware

from pretalx.common.forms.validators import (
    MaxDateTimeValidator,
    MaxDateValidator,
    MinDateTimeValidator,
    MinDateValidator,
    ZXCVBNValidator,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("min_score", "valid"),
    ((0, True), (1, True), (4, True), (-1, False), (5, False)),
    ids=("zero", "one", "four", "negative", "five"),
)
def test_zxcvbn_validator_init_score_range(min_score, valid):
    if valid:
        v = ZXCVBNValidator(min_score=min_score)
        assert v.min_score == min_score
    else:
        with pytest.raises(ValueError, match="min_score must be between 0 and 4"):
            ZXCVBNValidator(min_score=min_score)


def test_zxcvbn_validator_init_defaults():
    v = ZXCVBNValidator()

    assert v.min_score == 3
    assert v.user_attributes == ("name", "email")


def test_zxcvbn_validator_init_custom_user_attributes():
    v = ZXCVBNValidator(user_attributes=("username",))

    assert v.user_attributes == ("username",)


def test_zxcvbn_validator_validate_rejects_weak_password():
    v = ZXCVBNValidator(min_score=3)

    with pytest.raises(ValidationError):
        v.validate("password")


def test_zxcvbn_validator_validate_accepts_strong_password():
    v = ZXCVBNValidator(min_score=3)

    v.validate("c0rrect-h0rse-b@ttery-staple!")


def test_zxcvbn_validator_validate_uses_user_attributes():
    """A password based on user attributes should be penalised."""
    user = UserFactory.build(name="correcthorse", email="user@example.com")
    v = ZXCVBNValidator(min_score=4)

    with pytest.raises(ValidationError):
        v.validate("correcthorse", user=user)


def test_zxcvbn_validator_validate_ignores_none_user_attributes():
    """None attribute values should be filtered out, not passed to zxcvbn."""
    user = UserFactory.build(name=None, email=None)
    v = ZXCVBNValidator(min_score=1)

    v.validate("c0rrect-h0rse-b@ttery-staple!", user=user)


def test_zxcvbn_validator_callable_rejects_weak_password():
    v = ZXCVBNValidator(min_score=3)

    with pytest.raises(ValidationError):
        v("password")


@pytest.mark.parametrize(
    ("validator_class", "limit", "valid_value"),
    (
        (MinDateValidator, dt.date(2024, 1, 1), dt.date(2024, 6, 15)),
        (MaxDateValidator, dt.date(2024, 12, 31), dt.date(2024, 6, 15)),
        (
            MinDateTimeValidator,
            make_aware(dt.datetime(2024, 1, 1, 12, 0)),
            make_aware(dt.datetime(2024, 6, 15, 12, 0)),
        ),
        (
            MaxDateTimeValidator,
            make_aware(dt.datetime(2024, 12, 31, 23, 59)),
            make_aware(dt.datetime(2024, 6, 15, 12, 0)),
        ),
    ),
    ids=["min_date", "max_date", "min_datetime", "max_datetime"],
)
def test_date_validator_accepts_value_within_limit(validator_class, limit, valid_value):
    v = validator_class(limit)

    v(valid_value)


@pytest.mark.parametrize(
    ("validator_class", "limit", "invalid_value"),
    (
        (MinDateValidator, dt.date(2024, 1, 1), dt.date(2023, 12, 31)),
        (MaxDateValidator, dt.date(2024, 12, 31), dt.date(2025, 1, 1)),
        (
            MinDateTimeValidator,
            make_aware(dt.datetime(2024, 1, 1, 12, 0)),
            make_aware(dt.datetime(2023, 12, 31, 12, 0)),
        ),
        (
            MaxDateTimeValidator,
            make_aware(dt.datetime(2024, 12, 31, 23, 59)),
            make_aware(dt.datetime(2025, 1, 1, 0, 0)),
        ),
    ),
    ids=["min_date", "max_date", "min_datetime", "max_datetime"],
)
def test_date_validator_raises_with_formatted_limit(
    validator_class, limit, invalid_value
):
    v = validator_class(limit)

    with pytest.raises(ValidationError) as exc_info:
        v(invalid_value)

    assert "limit_value" in exc_info.value.params
    assert isinstance(exc_info.value.params["limit_value"], str)
