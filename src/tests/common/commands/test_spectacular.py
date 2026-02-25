from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_spectacular_command_generates_openapi_schema():
    out = StringIO()

    call_command("spectacular", stdout=out)
    schema = out.getvalue()

    assert "openapi" in schema
