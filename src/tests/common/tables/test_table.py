# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.mail import MailTemplateTable
from tests.utils import make_orga_user, make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_table_reflects_the_ordering_of_a_queryset_with_a_tiebreaker(event):
    queryset = event.mail_templates.order_by("role", "pk")

    table = MailTemplateTable(queryset, event=event)

    assert table.current_ordering == [{"column": "role", "direction": "asc"}]


def test_table_user_sort_is_deterministic_without_showing_the_tiebreaker(event):
    user = make_orga_user(event)
    request = make_request(event, user, path="/?sort=-role")
    table = MailTemplateTable(event.mail_templates.all(), event=event)

    table.configure(request)

    assert table.data.data.totally_ordered
    assert table.current_ordering == [{"column": "role", "direction": "desc"}]
