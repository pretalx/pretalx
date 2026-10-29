# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.speaker import SpeakerSearchFilter, SpeakerViewSet
from pretalx.submission.models import SubmissionStates
from tests.factories import SpeakerRoleFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("can_change", "expected_fields"),
    ((True, ("effective_name", "effective_email")), (False, ("effective_name",))),
    ids=["orga_includes_email", "non_orga_excludes_email"],
)
def test_speaker_search_filter_get_search_fields(can_change, expected_fields):
    view = SpeakerViewSet()
    # cached_property stores on the instance dict, so direct assignment works
    view.can_change_submissions = can_change

    search_filter = SpeakerSearchFilter()
    result = search_filter.get_search_fields(view, request=None)

    assert result == expected_fields


def test_speaker_viewset_can_change_submissions(event, orga_user):
    orga_view = make_view(SpeakerViewSet, make_api_request(event=event, user=orga_user))
    anonymous_view = make_view(SpeakerViewSet, make_api_request(event=event))

    assert orga_view.can_change_submissions is True
    assert anonymous_view.can_change_submissions is False


def test_speaker_viewset_get_serializer_context_needs_event(event, orga_user):
    role = SpeakerRoleFactory(
        submission__event=event,
        submission__state=SubmissionStates.CONFIRMED,
        speaker__event=event,
    )
    orga_view = make_view(SpeakerViewSet, make_api_request(event=event, user=orga_user))
    no_event_view = make_view(SpeakerViewSet, make_api_request())
    for view in (orga_view, no_event_view):
        view.format_kwarg = None

    orga_context = orga_view.get_serializer_context()
    no_event_context = no_event_view.get_serializer_context()

    assert list(orga_context["questions"]) == []
    assert list(orga_context["submissions"]) == [role.submission]
    assert orga_context["public_tags"] is False
    assert orga_context["public_resources"] is False
    assert "questions" not in no_event_context
    assert "submissions" not in no_event_context


def test_speaker_viewset_get_queryset_returns_speakers_for_user(event, orga_user):
    role = SpeakerRoleFactory(
        submission__event=event,
        submission__state=SubmissionStates.CONFIRMED,
        speaker__event=event,
    )
    orga_view = make_view(SpeakerViewSet, make_api_request(event=event, user=orga_user))
    no_event_view = make_view(SpeakerViewSet, make_api_request())
    for view in (orga_view, no_event_view):
        view.api_version = "v2"

    assert list(orga_view.get_queryset()) == [role.speaker]
    assert list(no_event_view.get_queryset()) == []
