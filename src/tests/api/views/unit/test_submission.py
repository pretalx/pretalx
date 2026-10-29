# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import serializers

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


@pytest.mark.parametrize(
    "data",
    (
        {"email": "speaker@example.com"},
        {"email": "speaker@example.com", "name": "Jane Doe", "locale": "de"},
        {"email": "speaker@example.com", "name": "", "locale": None},
        {"email": "speaker@example.com", "name": None, "locale": ""},
    ),
    ids=[
        "email_only",
        "all_fields",
        "blank_name_null_locale",
        "null_name_blank_locale",
    ],
)
def test_add_speaker_serializer_valid(data):
    serializer = AddSpeakerSerializer(data=data)

    assert serializer.is_valid()
    assert dict(serializer.validated_data) == data


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        pytest.param(
            {"name": "Jane Doe"},
            {"email": ["This field is required."]},
            id="missing-email",
        ),
        pytest.param(
            {"email": "not-an-email"},
            {"email": ["Enter a valid email address."]},
            id="malformed-email",
        ),
        pytest.param(
            {"email": "speaker@example.com", "name": "x" * 121},
            {"name": ["Ensure this field has no more than 120 characters."]},
            id="name-over-model-max-length",
        ),
    ),
)
def test_add_speaker_serializer_invalid(data, errors):
    serializer = AddSpeakerSerializer(data=data)

    assert not serializer.is_valid()
    assert serializer.errors == errors


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        ({"user": "ABCDE"}, {}),
        ({"email": "x@y.com"}, {"user": ["This field is required."]}),
    ),
)
def test_remove_speaker_serializer(data, errors):
    serializer = RemoveSpeakerSerializer(data=data)

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


@pytest.mark.django_db
def test_submissionviewset_is_orga(event, organiser_user):
    views = {
        "orga": make_view(
            SubmissionViewSet, make_api_request(event=event, user=organiser_user)
        ),
        "anonymous": make_view(SubmissionViewSet, make_api_request(event=event)),
        "unprivileged": make_view(
            SubmissionViewSet, make_api_request(event=event, user=UserFactory())
        ),
        "no_event": make_view(SubmissionViewSet, make_api_request(user=UserFactory())),
    }

    assert views["orga"].is_orga is True
    assert views["anonymous"].is_orga is False
    assert views["unprivileged"].is_orga is False
    assert not views["no_event"].is_orga


@pytest.mark.django_db
def test_submissionviewset_speakers_for_user(event, organiser_user, submission):
    orga_view = make_view(
        SubmissionViewSet, make_api_request(event=event, user=organiser_user)
    )
    anonymous_view = make_view(SubmissionViewSet, make_api_request(event=event))
    no_event_view = make_view(SubmissionViewSet, make_api_request(user=UserFactory()))

    assert list(orga_view.speakers_for_user) == list(submission.speakers.all())
    assert list(anonymous_view.speakers_for_user) == []
    assert no_event_view.speakers_for_user is None


@pytest.mark.django_db
def test_submissionviewset_get_serializer_context(event, organiser_user, submission):
    orga_view = make_view(
        SubmissionViewSet, make_api_request(event=event, user=organiser_user)
    )
    user_view = make_view(
        SubmissionViewSet, make_api_request(event=event, user=UserFactory())
    )
    no_event_view = make_view(SubmissionViewSet, make_api_request(user=UserFactory()))
    for view in (orga_view, user_view, no_event_view):
        view.format_kwarg = None

    orga_context = orga_view.get_serializer_context()
    user_context = user_view.get_serializer_context()
    no_event_context = no_event_view.get_serializer_context()

    assert list(orga_context["questions"]) == []
    assert list(orga_context["speakers"]) == list(submission.speakers.all())
    assert orga_context["schedule"] == event.current_schedule
    assert orga_context["public_slots"] is False
    assert orga_context["public_resources"] is False
    assert orga_context["public_tags"] is False
    assert user_context["public_slots"] is True
    assert user_context["public_resources"] is True
    assert user_context["public_tags"] is True
    assert "questions" not in no_event_context
    assert "speakers" not in no_event_context


@pytest.mark.django_db
def test_submissionviewset_get_queryset_by_role(
    event, organiser_user, review_user, submission, other_submission
):
    submission.speakers.add(SpeakerFactory(event=event, user=review_user))
    views = {
        "orga": make_view(
            SubmissionViewSet, make_api_request(event=event, user=organiser_user)
        ),
        "reviewer": make_view(
            SubmissionViewSet, make_api_request(event=event, user=review_user)
        ),
        "unprivileged": make_view(
            SubmissionViewSet, make_api_request(event=event, user=UserFactory())
        ),
        "anonymous": make_view(SubmissionViewSet, make_api_request(event=event)),
        "no_event": make_view(SubmissionViewSet, make_api_request(user=UserFactory())),
    }
    querysets = {role: view.get_queryset() for role, view in views.items()}

    assert list(querysets["orga"]) == sorted(
        [submission, other_submission], key=lambda sub: sub.code
    )
    assert list(querysets["reviewer"]) == [other_submission]
    assert list(querysets["unprivileged"]) == []
    assert list(querysets["anonymous"]) == []
    assert list(querysets["no_event"]) == []
    orga_prefetches = {
        getattr(lookup, "prefetch_through", lookup)
        for lookup in querysets["orga"]._prefetch_related_lookups
    }
    reviewer_prefetches = {
        getattr(lookup, "prefetch_through", lookup)
        for lookup in querysets["reviewer"]._prefetch_related_lookups
    }
    assert {"reviews", "invitations", "assigned_reviewers"} <= orga_prefetches
    assert {
        "reviews",
        "invitations",
        "assigned_reviewers",
    } & reviewer_prefetches == set()


@pytest.mark.django_db
def test_tagviewset_get_queryset_returns_event_tags_by_pk(event):
    tag1 = TagFactory(event=event)
    tag2 = TagFactory(event=event)
    TagFactory()

    request = make_api_request(event=event)
    view = make_view(TagViewSet, request)

    assert list(view.get_queryset()) == [tag1, tag2]


@pytest.mark.django_db
def test_submissiontypeviewset_get_queryset_returns_event_types(event):
    custom_type = SubmissionTypeFactory(event=event, name="Workshop")
    SubmissionTypeFactory()

    request = make_api_request(event=event)
    view = make_view(SubmissionTypeViewSet, request)

    assert set(view.get_queryset()) == {event.cfp.default_type, custom_type}


@pytest.mark.django_db
def test_trackviewset_get_queryset_returns_event_tracks(event, track):
    track2 = TrackFactory(event=event)
    TrackFactory()

    request = make_api_request(event=event)
    view = make_view(TrackViewSet, request)

    assert set(view.get_queryset()) == {track, track2}


@pytest.mark.django_db
def test_submissiontypeviewset_perform_destroy_rejects_used_type(event):
    st = SubmissionTypeFactory(event=event)
    SubmissionFactory(event=event, submission_type=st)
    request = make_api_request(event=event)
    view = make_view(SubmissionTypeViewSet, request)

    with pytest.raises(serializers.ValidationError):
        view.perform_destroy(st)


@pytest.mark.django_db
def test_trackviewset_perform_destroy_rejects_used_track(event, track):
    SubmissionFactory(event=event, track=track)
    request = make_api_request(event=event)
    view = make_view(TrackViewSet, request)

    with pytest.raises(serializers.ValidationError):
        view.perform_destroy(track)
