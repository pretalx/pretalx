# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.event import EventViewSet
from tests.factories import EventFactory, TeamFactory, UserFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_viewset_get_queryset_anonymous_sees_only_public():
    public_event = EventFactory(is_public=True)
    EventFactory(is_public=False)
    request = make_api_request()
    view = make_view(EventViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [public_event]


def test_event_viewset_get_queryset_orga_sees_private_events():
    public_event = EventFactory(is_public=True)
    private_event = EventFactory(is_public=False)
    user = UserFactory()
    team = TeamFactory(organiser=private_event.organiser, all_events=True)
    team.members.add(user)
    request = make_api_request(user=user)
    view = make_view(EventViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert set(qs) == {public_event, private_event}
