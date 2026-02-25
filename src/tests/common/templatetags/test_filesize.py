import pytest

from pretalx.common.templatetags.filesize import filesize

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("size", "expected"),
    (
        (0, "0.0B"),
        (100, "100.0B"),
        (1023, "1023.0B"),
        (1024, "1.0KB"),
        (1048576, "1.0MB"),
        (1073741824, "1.0GB"),
        (1099511627776, "1.0TB"),
        (1024**8, "1.0YiB"),
        ("invalid", ""),
        (None, ""),
    ),
)
def test_filesize(size, expected):
    assert filesize(size) == expected
