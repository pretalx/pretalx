import pytest
from django_scopes import scope, scopes_disabled

from pretalx.api.serializers.legacy import (
    LegacySpeakerOrgaSerializer,
    LegacySpeakerReviewerSerializer,
    LegacySpeakerSerializer,
)
from pretalx.api.serializers.speaker import (
    SpeakerOrgaSerializer,
    SpeakerSerializer,
    SpeakerUpdateSerializer,
)
from pretalx.api.versions import LEGACY
from pretalx.api.views.speaker import SpeakerSearchFilter, SpeakerViewSet
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_orga", "expected_fields"),
    ((True, ("name", "user__name", "user__email")), (False, ("name", "user__name"))),
    ids=["orga_includes_email", "non_orga_excludes_email"],
)
def test_speaker_search_filter_get_search_fields(event, is_orga, expected_fields):
    """SpeakerSearchFilter includes email in search fields only for organisers."""
    view = SpeakerViewSet()
    # cached_property stores on the instance dict, so direct assignment works
    view.is_orga = is_orga

    search_filter = SpeakerSearchFilter()
    result = search_filter.get_search_fields(view, request=None)

    assert result == expected_fields


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("has_perm", "expected"),
    ((True, True), (False, False)),
    ids=["orga_user", "anonymous_user"],
)
def test_speaker_viewset_is_orga(event, has_perm, expected):
    """is_orga returns True when user has orga_list_submission permission."""
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "expected_serializer"),
    (("GET", SpeakerOrgaSerializer), ("PATCH", SpeakerUpdateSerializer)),
    ids=[
        "safe_method_returns_orga_serializer",
        "unsafe_method_returns_update_serializer",
    ],
)
def test_speaker_viewset_get_unversioned_serializer_class_orga(
    event, method, expected_serializer
):
    """Orga users get SpeakerOrgaSerializer for safe requests, SpeakerUpdateSerializer for unsafe."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    request = make_api_request(event=event, user=user)
    request._request.method = method
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    result = view.get_unversioned_serializer_class()

    assert result is expected_serializer


@pytest.mark.django_db
def test_speaker_viewset_get_unversioned_serializer_class_non_orga(event):
    """Non-orga users get the base SpeakerSerializer."""
    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    result = view.get_unversioned_serializer_class()

    assert result is SpeakerSerializer


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_speaker_viewset_get_legacy_serializer_class_reviewer(event):
    """Reviewers with visible speaker names get LegacySpeakerReviewerSerializer."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_speaker_viewset_get_legacy_serializer_class_no_perms(event):
    """Users without orga or reviewer permissions get LegacySpeakerSerializer."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    assert view.get_legacy_serializer_class() is LegacySpeakerSerializer


@pytest.mark.django_db
def test_speaker_viewset_get_legacy_queryset_orga(event):
    """Orga users get all submitters for the event in legacy mode."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    with scopes_disabled():
        result = list(view.get_legacy_queryset())

    assert result == [speaker]


@pytest.mark.django_db
def test_speaker_viewset_get_legacy_queryset_public_with_schedule(event):
    """Anonymous users with a published schedule get published speakers."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)

    with scopes_disabled():
        result = list(view.get_legacy_queryset())

    assert result == [speaker]


@pytest.mark.django_db
def test_speaker_viewset_get_legacy_queryset_no_access(event):
    """Anonymous users without public schedule get an empty queryset."""
    event.feature_flags["show_schedule"] = False
    event.save()

    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)

    with scopes_disabled():
        result = list(view.get_legacy_queryset())

    assert result == []


@pytest.mark.django_db
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

    with scopes_disabled():
        context = view.get_serializer_context()

    assert "questions" in context
    assert "submissions" in context


@pytest.mark.django_db
def test_speaker_viewset_get_serializer_context_no_event():
    """get_serializer_context returns basic context when event is None (API docs)."""
    request = make_api_request()
    view = make_view(SpeakerViewSet, request)
    view.format_kwarg = None

    with scopes_disabled():
        context = view.get_serializer_context()

    assert "questions" not in context
    assert "submissions" not in context


@pytest.mark.django_db
def test_speaker_viewset_get_queryset_no_event():
    """get_queryset returns empty queryset when event is None (API docs)."""
    request = make_api_request()
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_speaker_viewset_get_queryset_returns_speakers_for_user(event):
    """get_queryset returns speakers visible to the requesting user."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)
    view.api_version = "v2"

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [speaker]


@pytest.mark.django_db
def test_speaker_viewset_submissions_for_user_property(event):
    """submissions_for_user returns the correct submissions for the user."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    with scopes_disabled():
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)

    with scopes_disabled():
        result = list(view.submissions_for_user)

    assert result == [sub]


@pytest.mark.django_db
def test_speaker_viewset_get_unversioned_serializer_class_legacy(event):
    """Legacy API version delegates to get_legacy_serializer_class."""
    request = make_api_request(event=event)
    view = make_view(SpeakerViewSet, request)
    view.api_version = LEGACY

    result = view.get_unversioned_serializer_class()

    assert result is LegacySpeakerSerializer


@pytest.mark.django_db
def test_speaker_viewset_get_queryset_legacy(event):
    """Legacy API version uses get_legacy_queryset with select_related."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)

    request = make_api_request(event=event, user=user)
    view = make_view(SpeakerViewSet, request)
    view.api_version = LEGACY

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [speaker]
