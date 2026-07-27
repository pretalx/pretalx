# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.speaker import SpeakerSearchFilter, SpeakerViewSet
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    SpeakerRoleFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("can_change", "expected_fields"),
    ((True, ("name", "user__name", "user__email")), (False, ("name", "user__name"))),
    ids=["orga_includes_email", "non_orga_excludes_email"],
)
def test_speaker_search_filter_get_search_fields(event, can_change, expected_fields):
    view = SpeakerViewSet()
    # cached_property stores on the instance dict, so direct assignment works
    view.can_change_submissions = can_change

    search_filter = SpeakerSearchFilter()
    result = search_filter.get_search_fields(view, request=None)

    assert result == expected_fields


@pytest.mark.parametrize(
    ("has_perm", "expected"),
    ((True, True), (False, False)),
    ids=["orga_user", "anonymous_user"],
)
def test_speaker_viewset_can_change_submissions(event, has_perm, expected):
    if has_perm:
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(user)
    else:
        user = None  # make_api_request defaults to AnonymousUser

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    assert view.can_change_submissions is expected


def test_speaker_viewset_get_serializer_context_includes_questions_and_submissions(
    event,
):
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert "questions" in context
    assert "submissions" in context


def test_speaker_viewset_get_serializer_context_no_event():
    request = make_api_request()
    view = make_view(SpeakerViewSet, request)
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert "questions" not in context
    assert "submissions" not in context


def test_speaker_viewset_get_queryset_no_event():
    request = make_api_request()
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    result = list(view.get_queryset())

    assert result == []


def test_speaker_viewset_get_queryset_returns_speakers_for_user(event):
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    role = SpeakerRoleFactory(
        submission__event=event,
        submission__state=SubmissionStates.CONFIRMED,
        speaker__event=event,
    )
    speaker = role.speaker

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    result = list(view.get_queryset())

    assert result == [speaker]


def test_speaker_viewset_submissions_for_user_property(event):
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    result = list(view.submissions_for_user)

    assert result == [sub]
