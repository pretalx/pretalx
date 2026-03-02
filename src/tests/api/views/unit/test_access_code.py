# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.views.access_code import SubmitterAccessCodeViewSet
from tests.factories import SubmissionFactory, SubmitterAccessCodeFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_access_code_viewset_get_queryset_returns_event_codes():
    code = SubmitterAccessCodeFactory()
    other_code = SubmitterAccessCodeFactory()
    request = make_api_request(event=code.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [code]
    assert other_code not in qs


def test_access_code_viewset_get_queryset_orders_by_pk():
    code1 = SubmitterAccessCodeFactory()
    code2 = SubmitterAccessCodeFactory(event=code1.event)
    request = make_api_request(event=code1.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [code1, code2]


def test_access_code_viewset_perform_destroy_deletes_code():
    code = SubmitterAccessCodeFactory()
    user = make_orga_user(code.event, can_change_event_settings=True)
    code.log_action("pretalx.access_code.create", person=user)
    code_pk = code.pk
    request = make_api_request(event=code.event, user=user)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "destroy"

    view.perform_destroy(code)
    assert not code.event.submitter_access_codes.filter(pk=code_pk).exists()


def test_access_code_viewset_perform_destroy_raises_when_used():
    code = SubmitterAccessCodeFactory()
    SubmissionFactory(event=code.event, access_code=code)
    request = make_api_request(event=code.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "destroy"

    with pytest.raises(exceptions.ValidationError, match="cannot delete"):
        view.perform_destroy(code)
