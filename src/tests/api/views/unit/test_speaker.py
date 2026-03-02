# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.api.serializers.legacy import (
    LegacySpeakerOrgaSerializer,
    LegacySpeakerReviewerSerializer,
    LegacySpeakerSerializer,
)
from pretalx.api.versions import LEGACY
from pretalx.api.views.speaker import SpeakerSearchFilter, SpeakerViewSet
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("is_orga", "expected_fields"),
    ((True, ("name", "user__name", "user__email")), (False, ("name", "user__name"))),
    ids=["orga_includes_email", "non_orga_excludes_email"],
)
def test_speaker_search_filter_get_search_fields(event, is_orga, expected_fields):
    view = SpeakerViewSet()
    # cached_property stores on the instance dict, so direct assignment works
    view.is_orga = is_orga

    search_filter = SpeakerSearchFilter()
    result = search_filter.get_search_fields(view, request=None)

    assert result == expected_fields


@pytest.mark.parametrize(
    ("has_perm", "expected"),
    ((True, True), (False, False)),
    ids=["orga_user", "anonymous_user"],
)
def test_speaker_viewset_is_orga(event, has_perm, expected):
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

    assert view.is_orga is expected


def test_speaker_viewset_get_legacy_serializer_class_orga(event):
    """Orga users with can_change_submissions get LegacySpeakerOrgaSerializer."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    assert view.get_legacy_serializer_class() is LegacySpeakerOrgaSerializer


def test_speaker_viewset_get_legacy_serializer_class_reviewer(event):
    """Reviewers with visible speaker names get LegacySpeakerReviewerSerializer."""
    phase = event.active_review_phase
    phase.can_see_speaker_names = True
    phase.save()
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_submissions=False,
        is_reviewer=True,
    )
    team.members.add(user)
    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    assert view.get_legacy_serializer_class() is LegacySpeakerReviewerSerializer


def test_speaker_viewset_get_legacy_serializer_class_no_perms(event):
    """Users without orga or reviewer permissions get LegacySpeakerSerializer."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    assert view.get_legacy_serializer_class() is LegacySpeakerSerializer


def test_speaker_viewset_get_legacy_queryset_orga(event):
    """Orga users get all submitters for the event in legacy mode."""
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

    result = list(view.get_legacy_queryset())

    assert result == [speaker]


def test_speaker_viewset_get_legacy_queryset_public_with_schedule():
    """Anonymous users with a published schedule get published speakers."""
    event = EventFactory(is_public=True)
    role = SpeakerRoleFactory(
        submission__event=event,
        submission__state=SubmissionStates.CONFIRMED,
        speaker__event=event,
    )
    speaker = role.speaker
    sub = role.submission
    TalkSlotFactory(submission=sub, is_visible=True)
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)

    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)

    result = list(view.get_legacy_queryset())

    assert result == [speaker]


def test_speaker_viewset_get_legacy_queryset_no_access():
    """Anonymous users without public schedule get an empty queryset."""
    event = EventFactory(feature_flags={"show_schedule": False})

    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)

    result = list(view.get_legacy_queryset())

    assert result == []


def test_speaker_viewset_get_serializer_context_includes_questions_and_submissions(
    event,
):
    """get_serializer_context provides questions and submissions for the user."""
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
    """get_serializer_context returns basic context when event is None (API docs)."""
    request = make_api_request()
    view = make_view(SpeakerViewSet, request)
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert "questions" not in context
    assert "submissions" not in context


def test_speaker_viewset_get_queryset_no_event():
    """get_queryset returns empty queryset when event is None (API docs)."""
    request = make_api_request()
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    result = list(view.get_queryset())

    assert result == []


def test_speaker_viewset_get_queryset_returns_speakers_for_user(event):
    """get_queryset returns speakers visible to the requesting user."""
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
    """submissions_for_user returns the correct submissions for the user."""
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


def test_speaker_viewset_get_unversioned_serializer_class_legacy(event):
    """Legacy API version delegates to get_legacy_serializer_class."""
    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)
    view.api_version = LEGACY

    result = view.get_unversioned_serializer_class()

    assert result is LegacySpeakerSerializer


def test_speaker_viewset_get_queryset_legacy(event):
    """Legacy API version uses get_legacy_queryset with select_related."""
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
    view.api_version = LEGACY

    result = list(view.get_queryset())

    assert result == [speaker]
