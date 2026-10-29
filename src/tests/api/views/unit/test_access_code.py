# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.views.access_code import SubmitterAccessCodeViewSet
from tests.factories import SubmissionFactory, SubmitterAccessCodeFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_access_code_viewset_get_queryset_returns_event_codes_by_pk():
    code1 = SubmitterAccessCodeFactory()
    code2 = SubmitterAccessCodeFactory(event=code1.event)
    SubmitterAccessCodeFactory()
    request = make_api_request(event=code1.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "list"

    assert list(view.get_queryset()) == [code1, code2]


def test_access_code_viewset_perform_destroy_rejects_used_code():
    unused = SubmitterAccessCodeFactory()
    used = SubmitterAccessCodeFactory(event=unused.event)
    SubmissionFactory(event=used.event, access_code=used)
    user = make_orga_user(used.event, can_change_event_settings=True)
    request = make_api_request(event=used.event, user=user)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "destroy"

    with pytest.raises(exceptions.ValidationError, match="cannot delete"):
        view.perform_destroy(used)
    view.perform_destroy(unused)

    assert list(used.event.submitter_access_codes.all()) == [used]
