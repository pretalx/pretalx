# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.speaker_information import SpeakerInformationViewSet
from tests.factories import EventFactory, SpeakerInformationFactory, TrackFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speakerinformationviewset_get_queryset_returns_event_information_by_pk(
    django_assert_num_queries,
):
    event = EventFactory()
    info1 = SpeakerInformationFactory(event=event)
    info2 = SpeakerInformationFactory(event=event)
    SpeakerInformationFactory()
    track = TrackFactory(event=event)
    info1.limit_tracks.add(track)
    request = make_api_request(event=event)
    view = make_view(SpeakerInformationViewSet, request)
    view.action = "list"

    items = list(view.get_queryset())

    assert items == [info1, info2]
    with django_assert_num_queries(0):
        assert list(items[0].limit_tracks.all()) == [track]
        assert list(items[0].limit_types.all()) == []
