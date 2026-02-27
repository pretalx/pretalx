import pytest
from django_scopes import scopes_disabled

from pretalx.api.serializers.submission import (
    SubmissionOrgaSerializer,
    SubmissionSerializer,
)
from pretalx.api.views.submission import (
    AddSpeakerSerializer,
    RemoveSpeakerSerializer,
    SubmissionTypeViewSet,
    SubmissionViewSet,
    TagViewSet,
    TrackViewSet,
)
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


def test_add_speaker_serializer_valid_with_email_only():
    """AddSpeakerSerializer accepts just an email address."""
    serializer = AddSpeakerSerializer(data={"email": "speaker@example.com"})

    assert serializer.is_valid()
    assert serializer.validated_data["email"] == "speaker@example.com"


def test_add_speaker_serializer_valid_with_all_fields():
    """AddSpeakerSerializer accepts email, name, and locale together."""
    serializer = AddSpeakerSerializer(
        data={"email": "speaker@example.com", "name": "Jane Doe", "locale": "de"}
    )

    assert serializer.is_valid()
    assert serializer.validated_data["email"] == "speaker@example.com"
    assert serializer.validated_data["name"] == "Jane Doe"
    assert serializer.validated_data["locale"] == "de"


def test_add_speaker_serializer_invalid_without_email():
    """AddSpeakerSerializer requires an email address."""
    serializer = AddSpeakerSerializer(data={"name": "Jane Doe"})

    assert not serializer.is_valid()
    assert "email" in serializer.errors


def test_add_speaker_serializer_invalid_email_format():
    """AddSpeakerSerializer rejects malformed email addresses."""
    serializer = AddSpeakerSerializer(data={"email": "not-an-email"})

    assert not serializer.is_valid()
    assert "email" in serializer.errors


@pytest.mark.parametrize(
    ("field", "value"), (("name", ""), ("name", None), ("locale", ""), ("locale", None))
)
def test_add_speaker_serializer_optional_field_accepts(field, value):
    """Name and locale fields accept blank strings and null values."""
    serializer = AddSpeakerSerializer(
        data={"email": "speaker@example.com", field: value}
    )

    assert serializer.is_valid()
    assert serializer.validated_data[field] == value


def test_remove_speaker_serializer_valid():
    """RemoveSpeakerSerializer accepts a user code string."""
    serializer = RemoveSpeakerSerializer(data={"user": "ABCDE"})

    assert serializer.is_valid()
    assert serializer.validated_data["user"] == "ABCDE"


def test_remove_speaker_serializer_invalid_without_user():
    """RemoveSpeakerSerializer requires a user field."""
    serializer = RemoveSpeakerSerializer(data={})

    assert not serializer.is_valid()
    assert "user" in serializer.errors


def test_remove_speaker_serializer_rejects_empty_data():
    """RemoveSpeakerSerializer rejects missing data entirely."""
    serializer = RemoveSpeakerSerializer(data={"email": "x@y.com"})

    assert not serializer.is_valid()
    assert "user" in serializer.errors


@pytest.mark.django_db
def test_submissionviewset_is_orga_true_for_organiser(event, organiser_user):
    """is_orga returns True for a user with orga_list_submission permission."""
    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)

    assert view.is_orga is True


@pytest.mark.django_db
def test_submissionviewset_is_orga_false_for_anonymous(event):
    """is_orga returns False for an anonymous user."""
    request = make_api_request(event=event)
    view = make_view(SubmissionViewSet, request)

    assert view.is_orga is False


@pytest.mark.django_db
def test_submissionviewset_is_orga_false_for_unprivileged_user(event):
    """is_orga returns False for a user without orga permissions."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SubmissionViewSet, request)

    assert view.is_orga is False


@pytest.mark.django_db
def test_submissionviewset_is_orga_falsy_when_no_event():
    """is_orga returns a falsy value when event is None (short-circuits)."""
    user = UserFactory()
    request = make_api_request(user=user)
    view = make_view(SubmissionViewSet, request)

    assert not view.is_orga


@pytest.mark.django_db
def test_submissionviewset_speakers_for_user_returns_profiles(
    event, organiser_user, submission
):
    """speakers_for_user returns speaker profiles visible to the user."""
    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.speakers_for_user)
        expected_speaker = submission.speakers.first()

    assert len(result) == 1
    assert result[0] == expected_speaker


@pytest.mark.django_db
def test_submissionviewset_speakers_for_user_none_without_event():
    """speakers_for_user returns None when event is None."""
    user = UserFactory()
    request = make_api_request(user=user)
    view = make_view(SubmissionViewSet, request)

    assert view.speakers_for_user is None


@pytest.mark.django_db
def test_submissionviewset_speakers_for_user_empty_for_anonymous(event):
    """speakers_for_user returns empty queryset for anonymous user with no schedule."""
    request = make_api_request(event=event)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.speakers_for_user)

    assert result == []


@pytest.mark.django_db
def test_submissionviewset_unversioned_serializer_orga(event, organiser_user):
    """Orga users get SubmissionOrgaSerializer."""
    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)

    result = view.get_unversioned_serializer_class()

    assert result is SubmissionOrgaSerializer


@pytest.mark.django_db
def test_submissionviewset_unversioned_serializer_non_orga(event):
    """Non-orga users get SubmissionSerializer."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SubmissionViewSet, request)

    result = view.get_unversioned_serializer_class()

    assert result is SubmissionSerializer


@pytest.mark.django_db
def test_submissionviewset_unversioned_serializer_anonymous(event):
    """Anonymous users get SubmissionSerializer."""
    request = make_api_request(event=event)
    view = make_view(SubmissionViewSet, request)

    result = view.get_unversioned_serializer_class()

    assert result is SubmissionSerializer


@pytest.mark.django_db
def test_submissionviewset_get_serializer_context_includes_expected_keys(
    event, organiser_user
):
    """get_serializer_context includes questions, speakers, schedule, public_slots, public_resources."""
    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)
    view.format_kwarg = None

    with scopes_disabled():
        context = view.get_serializer_context()

    assert {
        "questions",
        "speakers",
        "schedule",
        "public_slots",
        "public_resources",
    } <= set(context.keys())


@pytest.mark.django_db
def test_submissionviewset_get_serializer_context_without_event():
    """get_serializer_context works without an event (returns base context)."""
    user = UserFactory()
    request = make_api_request(user=user)
    view = make_view(SubmissionViewSet, request)
    view.format_kwarg = None

    with scopes_disabled():
        context = view.get_serializer_context()

    assert "questions" not in context
    assert "speakers" not in context


@pytest.mark.django_db
def test_submissionviewset_get_serializer_context_public_resources_true_for_non_orga(
    event,
):
    """Non-orga users get public_resources=True in context."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SubmissionViewSet, request)
    view.format_kwarg = None

    with scopes_disabled():
        context = view.get_serializer_context()

    assert context["public_resources"] is True


@pytest.mark.django_db
def test_submissionviewset_get_serializer_context_public_resources_false_for_orga(
    event, organiser_user
):
    """Orga users get public_resources=False in context."""
    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)
    view.format_kwarg = None

    with scopes_disabled():
        context = view.get_serializer_context()

    assert context["public_resources"] is False


@pytest.mark.django_db
def test_submissionviewset_get_serializer_context_schedule_is_current(event):
    """Context schedule matches event.current_schedule."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SubmissionViewSet, request)
    view.format_kwarg = None

    with scopes_disabled():
        context = view.get_serializer_context()

    assert context["schedule"] == event.current_schedule


@pytest.mark.django_db
def test_submissionviewset_get_queryset_empty_without_event():
    """get_queryset returns empty queryset when event is None."""
    user = UserFactory()
    request = make_api_request(user=user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_submissionviewset_get_queryset_empty_for_anonymous(event, submission):
    """Anonymous user gets empty queryset when no schedule is published."""
    request = make_api_request(event=event)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_submissionviewset_get_queryset_orga_sees_all_submissions(
    event, organiser_user, submission
):
    """Organiser sees all submissions on the event."""
    with scopes_disabled():
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)

    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert set(result) == {submission, other_sub}


@pytest.mark.django_db
def test_submissionviewset_get_queryset_unprivileged_user_no_schedule(
    event, submission
):
    """User without permissions and no published schedule gets empty queryset."""
    user = UserFactory()
    request = make_api_request(event=event, user=user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_submissionviewset_get_queryset_ordered_by_code(
    event, organiser_user, submission
):
    """Queryset is ordered by submission code."""
    with scopes_disabled():
        sub2 = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        sub2.speakers.add(speaker)

    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert set(result) == {submission, sub2}
    codes = [s.code for s in result]
    assert codes == sorted(codes)


def test_submissionviewset_lookup_field():
    """SubmissionViewSet uses code__iexact as lookup field."""
    assert SubmissionViewSet.lookup_field == "code__iexact"


@pytest.mark.parametrize(
    ("action_name", "expected_perm"),
    (
        ("make_submitted", "submission.state_change_submission"),
        ("accept", "submission.state_change_submission"),
        ("reject", "submission.state_change_submission"),
        ("confirm", "submission.state_change_submission"),
        ("cancel", "submission.state_change_submission"),
        ("add_speaker", "submission.update_submission"),
        ("remove_speaker", "submission.update_submission"),
        ("invite_speaker", "submission.update_submission"),
        ("retract_invitation", "submission.update_submission"),
        ("add_resource", "submission.update_submission"),
        ("remove_resource", "submission.update_submission"),
    ),
)
def test_submissionviewset_permission_map(action_name, expected_perm):
    """Each action maps to the correct permission."""
    assert SubmissionViewSet.permission_map[action_name] == expected_perm


@pytest.mark.django_db
def test_tagviewset_get_queryset_returns_event_tags(event, tag):
    """TagViewSet.get_queryset returns all tags for the event."""
    request = make_api_request(event=event)
    view = make_view(TagViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [tag]


@pytest.mark.django_db
def test_tagviewset_get_queryset_excludes_other_event_tags(event, tag):
    """TagViewSet.get_queryset does not include tags from other events."""
    with scopes_disabled():
        TagFactory()  # creates a tag on a different event

    request = make_api_request(event=event)
    view = make_view(TagViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [tag]


@pytest.mark.django_db
def test_tagviewset_get_queryset_empty_when_no_tags(event):
    """TagViewSet.get_queryset returns empty queryset when event has no tags."""
    request = make_api_request(event=event)
    view = make_view(TagViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_tagviewset_get_queryset_ordered_by_pk(event):
    """TagViewSet.get_queryset returns tags ordered by pk."""
    with scopes_disabled():
        TagFactory(event=event)
        TagFactory(event=event)
        TagFactory(event=event)

    request = make_api_request(event=event)
    view = make_view(TagViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    pks = [t.pk for t in result]
    assert pks == sorted(pks)
    assert len(result) == 3


@pytest.mark.django_db
def test_submissiontypeviewset_get_queryset_returns_event_types(event):
    """SubmissionTypeViewSet.get_queryset returns all submission types for the event."""
    request = make_api_request(event=event)
    view = make_view(SubmissionTypeViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())
        default_type = event.cfp.default_type

    assert result == [default_type]


@pytest.mark.django_db
def test_submissiontypeviewset_get_queryset_includes_custom_type(event):
    """SubmissionTypeViewSet.get_queryset includes custom submission types."""
    with scopes_disabled():
        default_type = event.cfp.default_type
        custom_type = SubmissionTypeFactory(event=event, name="Workshop")

    request = make_api_request(event=event)
    view = make_view(SubmissionTypeViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert set(result) == {default_type, custom_type}


@pytest.mark.django_db
def test_submissiontypeviewset_get_queryset_excludes_other_event_types(event):
    """SubmissionTypeViewSet.get_queryset does not include types from other events."""
    with scopes_disabled():
        default_type = event.cfp.default_type
        SubmissionTypeFactory()  # creates on a different event

    request = make_api_request(event=event)
    view = make_view(SubmissionTypeViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [default_type]


@pytest.mark.django_db
def test_trackviewset_get_queryset_returns_event_tracks(event, track):
    """TrackViewSet.get_queryset returns all tracks for the event."""
    request = make_api_request(event=event)
    view = make_view(TrackViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [track]


@pytest.mark.django_db
def test_trackviewset_get_queryset_excludes_other_event_tracks(event, track):
    """TrackViewSet.get_queryset does not include tracks from other events."""
    with scopes_disabled():
        TrackFactory()  # creates on a different event

    request = make_api_request(event=event)
    view = make_view(TrackViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [track]


@pytest.mark.django_db
def test_trackviewset_get_queryset_empty_when_no_tracks(event):
    """TrackViewSet.get_queryset returns empty queryset when event has no tracks."""
    request = make_api_request(event=event)
    view = make_view(TrackViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_trackviewset_get_queryset_multiple_tracks(event):
    """TrackViewSet.get_queryset returns all tracks when multiple exist."""
    with scopes_disabled():
        track1 = TrackFactory(event=event)
        track2 = TrackFactory(event=event)

    request = make_api_request(event=event)
    view = make_view(TrackViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert set(result) == {track1, track2}


@pytest.mark.django_db
def test_submissionviewset_get_queryset_reviewer_excludes_own_submissions(
    event, review_user, submission
):
    """Reviewer does not see submissions where they are a speaker."""
    with scopes_disabled():
        speaker_profile = SpeakerFactory(event=event, user=review_user)
        submission.speakers.add(speaker_profile)
        # Create another submission the reviewer should see
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)

    request = make_api_request(event=event, user=review_user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [other_sub]


@pytest.mark.django_db
def test_submissionviewset_get_queryset_orga_includes_prefetches(
    event, organiser_user, submission
):
    """Orga queryset includes orga-specific prefetches (reviews, invitations)."""
    request = make_api_request(event=event, user=organiser_user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        qs = view.get_queryset()
        # Force evaluation to trigger prefetches
        result = list(qs)

    assert len(result) == 1
    # Verify the queryset has the expected prefetches by checking the lookups
    prefetch_names = [
        p.prefetch_through if hasattr(p, "prefetch_through") else p
        for p in qs._prefetch_related_lookups
    ]
    assert "reviews" in prefetch_names
    assert "invitations" in prefetch_names
    assert "assigned_reviewers" in prefetch_names


@pytest.mark.django_db
def test_submissionviewset_get_queryset_non_orga_omits_orga_prefetches(
    event, submission
):
    """Non-orga queryset does not include orga-specific prefetches."""
    user = UserFactory()
    # Give the user schedule.list_schedule via a published schedule so they see something
    # but without orga permissions
    request = make_api_request(event=event, user=user)
    view = make_view(SubmissionViewSet, request)

    with scopes_disabled():
        qs = view.get_queryset()

    prefetch_names = [
        p.prefetch_through if hasattr(p, "prefetch_through") else p
        for p in qs._prefetch_related_lookups
    ]
    assert "reviews" not in prefetch_names
    assert "invitations" not in prefetch_names
    assert "assigned_reviewers" not in prefetch_names
