import pytest
from django_scopes import scopes_disabled

from pretalx.api.serializers.review import ReviewSerializer, ReviewWriteSerializer
from pretalx.api.views.review import ReviewViewSet
from tests.factories import SpeakerFactory, SubmissionFactory, UserFactory
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_reviewviewset_get_unversioned_serializer_class_for_read(event):
    """GET request returns ReviewSerializer."""
    request = make_api_request(event=event)
    request._request.method = "GET"
    view = make_view(ReviewViewSet, request)

    result = view.get_unversioned_serializer_class()

    assert result is ReviewSerializer


@pytest.mark.django_db
def test_reviewviewset_get_unversioned_serializer_class_for_write(event):
    """POST request returns ReviewWriteSerializer."""
    request = make_api_request(event=event)
    request._request.method = "POST"
    view = make_view(ReviewViewSet, request)

    result = view.get_unversioned_serializer_class()

    assert result is ReviewWriteSerializer


@pytest.mark.django_db
def test_reviewviewset_visible_submissions_excludes_speaker_talks(
    event, review_user, submission
):
    """Reviewer doesn't see submissions they are a speaker on."""
    # Add review_user as a speaker on the existing submission
    with scopes_disabled():
        speaker_profile = SpeakerFactory(event=event, user=review_user)
        submission.speakers.add(speaker_profile)
        # Create a second submission that review_user is NOT a speaker on
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)

    request = make_api_request(event=event, user=review_user)
    view = make_view(ReviewViewSet, request)

    with scopes_disabled():
        visible = list(view.visible_submissions)

    # The submission where review_user is a speaker should be excluded
    assert submission not in visible
    # The other submission should still be visible
    assert other_sub in visible


@pytest.mark.django_db
def test_reviewviewset_visible_submissions_organiser_sees_all(
    event, orga_user, submission
):
    """Organiser (non-reviewer-only) sees all submissions they're not a speaker on."""
    with scopes_disabled():
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)

    request = make_api_request(event=event, user=orga_user)
    view = make_view(ReviewViewSet, request)

    with scopes_disabled():
        visible = list(view.visible_submissions)

    # Organiser should see both submissions (neither has orga_user as speaker)
    assert submission in visible
    assert other_sub in visible


@pytest.mark.django_db
def test_reviewviewset_visible_submissions_empty_without_event(event):
    """Returns empty queryset when event is None."""
    user = UserFactory()
    request = make_api_request(user=user)
    # No event set on the request, so view.event will be None
    view = make_view(ReviewViewSet, request)

    with scopes_disabled():
        visible = list(view.visible_submissions)

    assert visible == []


@pytest.mark.django_db
def test_reviewviewset_get_queryset_empty_for_anonymous(event):
    """Anonymous user gets empty queryset."""
    request = make_api_request(event=event)
    # make_api_request without user leaves request.user as AnonymousUser
    view = make_view(ReviewViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_reviewviewset_get_queryset_empty_without_event():
    """get_queryset returns empty queryset when event is None."""
    user = UserFactory()
    request = make_api_request(user=user)
    view = make_view(ReviewViewSet, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == []
