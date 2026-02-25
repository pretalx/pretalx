import pytest

from pretalx.common.templatetags.times import times

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("input_value", "expected"),
    (
        (None, ""),
        (1, "once"),
        (2, "twice"),
        (3, "3 times"),
        (0, "0 times"),
        ("1", "once"),
        ("2", "twice"),
        ("3", "3 times"),
    ),
)
def test_times(input_value, expected):
    assert times(input_value) == expected
