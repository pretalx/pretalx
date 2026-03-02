# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.mail import MailTemplateViewSet
from tests.factories import MailTemplateFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_viewset_get_queryset_returns_event_templates():
    template = MailTemplateFactory()
    other_template = MailTemplateFactory()
    request = make_api_request(event=template.event)
    view = make_view(MailTemplateViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert template in qs
    assert other_template not in qs


def test_mail_template_viewset_get_queryset_orders_by_pk():
    t1 = MailTemplateFactory()
    t2 = MailTemplateFactory(event=t1.event)
    request = make_api_request(event=t1.event)
    view = make_view(MailTemplateViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    # Filter to just the templates we created (event has auto-created templates too)
    our_templates = [t for t in qs if t.pk in (t1.pk, t2.pk)]
    assert our_templates == [t1, t2]
