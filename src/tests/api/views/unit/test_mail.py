# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.mail import MailTemplateViewSet
from tests.factories import MailTemplateFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_viewset_get_queryset_returns_event_templates_by_pk():
    template1 = MailTemplateFactory()
    event = template1.event
    template2 = MailTemplateFactory(event=event)
    MailTemplateFactory()
    request = make_api_request(event=event)
    view = make_view(MailTemplateViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    # Auto-created templates come first
    assert qs[-2:] == [template1, template2]
    assert {template.event_id for template in qs} == {event.pk}
