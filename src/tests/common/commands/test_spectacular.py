# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.slow
def test_spectacular_command_generates_openapi_schema():
    out = StringIO()

    call_command("spectacular", stdout=out)
    schema = out.getvalue()

    assert "openapi" in schema
