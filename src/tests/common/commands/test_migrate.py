from io import StringIO

import pytest

from pretalx.common.management.commands.migrate import OutputFilter

pytestmark = pytest.mark.unit


def test_output_filter_write_passes_normal_message():
    out = StringIO()
    f = OutputFilter(out)

    f.write("Applying migrations...")

    assert out.getvalue() == "Applying migrations...\n"


@pytest.mark.parametrize(
    "banned_msg",
    (
        "Your models in app 'foo' have changes that are not yet reflected in a migration.",
        "Run 'manage.py makemigrations' to make new migrations.",
    ),
    ids=("changes_not_reflected", "run_makemigrations"),
)
def test_output_filter_write_blocks_banned_messages(banned_msg):
    out = StringIO()
    f = OutputFilter(out)

    f.write(banned_msg)

    assert out.getvalue() == ""
