import datetime as dt

import pytest
from django_scopes import scopes_disabled
from rest_framework.exceptions import ValidationError

from pretalx.api.serializers.submission import (
    ResourceSerializer,
    ResourceWriteSerializer,
    SubmissionInvitationSerializer,
    SubmissionOrgaSerializer,
    SubmissionSerializer,
    SubmissionTypeSerializer,
    TagSerializer,
    TrackSerializer,
)
from pretalx.event.models import Team
from pretalx.submission.models import (
    QuestionTarget,
    SubmissionInvitation,
    SubmissionStates,
)
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_resource_serializer_fields():
    with scopes_disabled():
        resource = ResourceFactory()
        request = make_api_request(resource.submission.event)

    serializer = ResourceSerializer(resource, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {"id", "resource", "description", "is_public"}
    assert data["id"] == resource.pk
    assert data["is_public"] is True


@pytest.mark.django_db
def test_resource_serializer_get_resource_returns_url():
    with scopes_disabled():
        resource = ResourceFactory(link="https://example.com/slides")
        request = make_api_request(resource.submission.event)

    serializer = ResourceSerializer(resource, context={"request": request})

    assert serializer.data["resource"] == "https://example.com/slides"


@pytest.mark.parametrize(
    ("data", "match"),
    (
        (
            {
                "resource": b"fakefile",
                "link": "https://example.com",
                "description": "d",
            },
            "not both",
        ),
        ({"resource": None, "link": "", "description": "d"}, "link or a file"),
    ),
    ids=("both_provided", "neither_provided"),
)
@pytest.mark.django_db
def test_resource_write_serializer_validate_rejects_invalid_input(data, match):
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    serializer = ResourceWriteSerializer(context={"request": request})

    with pytest.raises(ValidationError, match=match):
        serializer.validate(data)


@pytest.mark.django_db
def test_resource_write_serializer_validate_accepts_link_only():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    serializer = ResourceWriteSerializer(context={"request": request})

    result = serializer.validate(
        {"link": "https://example.com", "description": "slides"}
    )

    assert result["link"] == "https://example.com"


@pytest.mark.django_db
def test_resource_write_serializer_validate_accepts_file_only():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    serializer = ResourceWriteSerializer(context={"request": request})

    result = serializer.validate({"resource": b"data", "description": "file"})

    assert result["resource"] == b"data"


@pytest.mark.parametrize(
    ("extra_data", "expected_link"),
    (({"link": "https://example.com/slides"}, "https://example.com/slides"), ({}, "")),
    ids=("with_link", "without_link"),
)
@pytest.mark.django_db
def test_resource_write_serializer_create_link_handling(extra_data, expected_link):
    """The create method defaults link to '' when not provided, and preserves it otherwise."""
    with scopes_disabled():
        submission = SubmissionFactory()
    request = make_api_request(submission.event)
    serializer = ResourceWriteSerializer(context={"request": request})

    with scopes_disabled():
        resource = serializer.create(
            {
                "submission": submission,
                "resource": None,
                "description": "A resource",
                "is_public": True,
                **extra_data,
            }
        )

    assert resource.link == expected_link


@pytest.mark.django_db
def test_tag_serializer_fields():
    with scopes_disabled():
        tag = TagFactory()
        request = make_api_request(tag.event)

    serializer = TagSerializer(tag, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {"id", "tag", "description", "color", "is_public"}
    assert data["id"] == tag.pk
    assert data["color"] == tag.color


@pytest.mark.django_db
def test_tag_serializer_create_sets_event():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    serializer = TagSerializer(context={"request": request})

    with scopes_disabled():
        tag = serializer.create(
            {"tag": "python", "color": "#00ff00", "is_public": True}
        )

    assert tag.event == event


@pytest.mark.django_db
def test_tag_serializer_validate_tag_rejects_duplicate():
    with scopes_disabled():
        existing = TagFactory(tag="python")
        request = make_api_request(existing.event)
        serializer = TagSerializer(context={"request": request})

        with pytest.raises(ValidationError, match="already exists"):
            serializer.validate_tag("python")


@pytest.mark.django_db
def test_tag_serializer_validate_tag_allows_editing_own():
    with scopes_disabled():
        tag = TagFactory(tag="python")
        request = make_api_request(tag.event)
        serializer = TagSerializer(instance=tag, context={"request": request})

        result = serializer.validate_tag("python")

    assert result == "python"


@pytest.mark.django_db
def test_tag_serializer_validate_tag_rejects_duplicate_when_editing_other():
    with scopes_disabled():
        event = EventFactory()
        TagFactory(event=event, tag="python")
        other = TagFactory(event=event, tag="django")
        request = make_api_request(event)
        serializer = TagSerializer(instance=other, context={"request": request})

        with pytest.raises(ValidationError, match="already exists"):
            serializer.validate_tag("python")


@pytest.mark.django_db
def test_tag_serializer_validate_tag_accepts_unique():
    with scopes_disabled():
        event = EventFactory()
        TagFactory(event=event, tag="python")
        request = make_api_request(event)
        serializer = TagSerializer(context={"request": request})

        result = serializer.validate_tag("django")

    assert result == "django"


@pytest.mark.django_db
def test_submission_type_serializer_fields():
    with scopes_disabled():
        stype = SubmissionTypeFactory()
        request = make_api_request(stype.event)

    serializer = SubmissionTypeSerializer(stype, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {
        "id",
        "name",
        "default_duration",
        "deadline",
        "requires_access_code",
    }
    assert data["id"] == stype.pk
    assert data["default_duration"] == stype.default_duration


@pytest.mark.django_db
def test_submission_type_serializer_create_sets_event():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    serializer = SubmissionTypeSerializer(context={"request": request})

    with scopes_disabled():
        stype = serializer.create({"name": "Workshop", "default_duration": 90})

    assert stype.event == event


@pytest.mark.django_db
def test_submission_type_serializer_validate_name_rejects_duplicate():
    with scopes_disabled():
        event = EventFactory()
        SubmissionTypeFactory(event=event, name="Workshop")
        request = make_api_request(event)
        serializer = SubmissionTypeSerializer(context={"request": request})

        with pytest.raises(ValidationError, match="already exists"):
            serializer.validate_name("Workshop")


@pytest.mark.django_db
def test_submission_type_serializer_validate_name_allows_editing_own():
    with scopes_disabled():
        stype = SubmissionTypeFactory(name="Workshop")
        request = make_api_request(stype.event)
        serializer = SubmissionTypeSerializer(
            instance=stype, context={"request": request}
        )

        result = serializer.validate_name("Workshop")

    assert result == "Workshop"


@pytest.mark.django_db
def test_submission_type_serializer_validate_name_rejects_duplicate_when_editing_other():
    with scopes_disabled():
        event = EventFactory()
        SubmissionTypeFactory(event=event, name="Workshop")
        other = SubmissionTypeFactory(event=event, name="Lightning")
        request = make_api_request(event)
        serializer = SubmissionTypeSerializer(
            instance=other, context={"request": request}
        )

        with pytest.raises(ValidationError, match="already exists"):
            serializer.validate_name("Workshop")


@pytest.mark.django_db
def test_submission_type_serializer_update_propagates_duration_to_slots():
    """When default_duration changes, slot end times are updated for submissions
    that inherit their duration from the type (duration=None)."""
    with scopes_disabled():
        stype = SubmissionTypeFactory(default_duration=30)
        submission = SubmissionFactory(event=stype.event, submission_type=stype)
        start = submission.event.datetime_from
        slot = TalkSlotFactory(
            submission=submission, start=start, end=start + dt.timedelta(minutes=30)
        )
    request = make_api_request(stype.event)
    serializer = SubmissionTypeSerializer(instance=stype, context={"request": request})

    with scopes_disabled():
        serializer.update(stype, {"default_duration": 60})
        slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=60)


@pytest.mark.django_db
def test_submission_type_serializer_update_skips_update_duration_when_unchanged():
    """When default_duration stays the same, slot end times are not modified."""
    with scopes_disabled():
        stype = SubmissionTypeFactory(default_duration=30)
        submission = SubmissionFactory(event=stype.event, submission_type=stype)
        start = submission.event.datetime_from
        slot = TalkSlotFactory(
            submission=submission, start=start, end=start + dt.timedelta(minutes=30)
        )
    request = make_api_request(stype.event)
    serializer = SubmissionTypeSerializer(instance=stype, context={"request": request})

    with scopes_disabled():
        serializer.update(stype, {"default_duration": 30})
        slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=30)


@pytest.mark.django_db
def test_track_serializer_fields():
    with scopes_disabled():
        track = TrackFactory()
        request = make_api_request(track.event)

    serializer = TrackSerializer(track, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {
        "id",
        "name",
        "description",
        "color",
        "position",
        "requires_access_code",
    }
    assert data["id"] == track.pk
    assert data["color"] == track.color


@pytest.mark.django_db
def test_track_serializer_create_sets_event():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    serializer = TrackSerializer(context={"request": request})

    with scopes_disabled():
        track = serializer.create(
            {"name": "Security", "color": "#ff0000", "position": 0}
        )

    assert track.event == event


@pytest.mark.django_db
def test_track_serializer_validate_name_rejects_duplicate():
    with scopes_disabled():
        track = TrackFactory(name="Security")
        request = make_api_request(track.event)
        serializer = TrackSerializer(context={"request": request})

        with pytest.raises(ValidationError, match="already exists"):
            serializer.validate_name("Security")


@pytest.mark.django_db
def test_track_serializer_validate_name_allows_editing_own():
    with scopes_disabled():
        track = TrackFactory(name="Security")
        request = make_api_request(track.event)
        serializer = TrackSerializer(instance=track, context={"request": request})

        result = serializer.validate_name("Security")

    assert result == "Security"


@pytest.mark.django_db
def test_track_serializer_validate_name_rejects_duplicate_when_editing_other():
    with scopes_disabled():
        event = EventFactory()
        TrackFactory(event=event, name="Security")
        other = TrackFactory(event=event, name="DevOps")
        request = make_api_request(event)
        serializer = TrackSerializer(instance=other, context={"request": request})

        with pytest.raises(ValidationError, match="already exists"):
            serializer.validate_name("Security")


@pytest.mark.django_db
def test_submission_invitation_serializer_fields():
    with scopes_disabled():
        submission = SubmissionFactory()
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="speaker@example.com"
        )
        request = make_api_request(submission.event)

    serializer = SubmissionInvitationSerializer(
        invitation, context={"request": request}
    )
    data = serializer.data

    assert set(data.keys()) == {"id", "email", "created", "updated"}
    assert data["id"] == invitation.pk
    assert data["email"] == "speaker@example.com"


@pytest.mark.django_db
def test_submission_serializer_init_sets_querysets():
    with scopes_disabled():
        event = EventFactory()
        stype = event.cfp.default_type
        track = TrackFactory(event=event)
        tag = TagFactory(event=event)
        event.feature_flags["use_tracks"] = True
        event.save()
        request = make_api_request(event)
        serializer = SubmissionSerializer(context={"request": request})

        assert list(serializer.fields["submission_type"].queryset) == [stype]
        assert list(serializer.fields["track"].queryset) == [track]
        assert list(serializer.fields["tags"].queryset) == [tag]


@pytest.mark.django_db
def test_submission_serializer_init_removes_track_when_feature_disabled():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()
        request = make_api_request(event)
        serializer = SubmissionSerializer(context={"request": request})

    assert "track" not in serializer.fields


@pytest.mark.django_db
def test_submission_serializer_init_removes_unrequested_cfp_fields():
    """Fields not requested in CfP config are removed from the serializer."""
    with scopes_disabled():
        event = EventFactory()
        cfp = event.cfp
        cfp.fields["description"] = {"visibility": "do_not_ask"}
        cfp.save()
        request = make_api_request(event)
        serializer = SubmissionSerializer(context={"request": request})

    assert "description" not in serializer.fields


@pytest.mark.django_db
def test_submission_serializer_init_sets_field_required_from_cfp():
    """Fields marked 'required' in CfP should be required in serializer."""
    with scopes_disabled():
        event = EventFactory()
        cfp = event.cfp
        cfp.fields["abstract"] = {"visibility": "required"}
        cfp.fields["description"] = {"visibility": "optional"}
        cfp.save()
        request = make_api_request(event)
        serializer = SubmissionSerializer(context={"request": request})

    assert serializer.fields["abstract"].required is True
    assert serializer.fields["description"].required is False


@pytest.mark.django_db
def test_submission_serializer_init_without_event():
    """When no event is in the request context, __init__ returns early."""
    request = make_api_request(event=None)

    serializer = SubmissionSerializer(context={"request": request})

    assert serializer.event is None


@pytest.mark.django_db
def test_submission_serializer_fields():
    with scopes_disabled():
        submission = SubmissionFactory()
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission, context={"request": request, "questions": [], "schedule": None}
        )
        data = serializer.data

    expected_keys = {
        "code",
        "title",
        "speakers",
        "submission_type",
        "state",
        "abstract",
        "duration",
        "slot_count",
        "content_locale",
        "do_not_record",
        "resources",
        "slots",
        "answers",
    }
    assert expected_keys <= set(data.keys())
    assert data["code"] == submission.code
    assert data["title"] == str(submission.title)


@pytest.mark.django_db
def test_submission_serializer_get_speakers_returns_codes():
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker)
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(submission, context={"request": request})
        data = serializer.data

    assert data["speakers"] == [speaker.code]


@pytest.mark.django_db
def test_submission_serializer_get_speakers_without_event():
    with scopes_disabled():
        submission = SubmissionFactory()
    request = make_api_request(event=None)

    serializer = SubmissionSerializer(submission, context={"request": request})

    assert serializer.get_speakers(submission) == []


@pytest.mark.django_db
def test_submission_serializer_get_answers_filters_by_submission_questions():
    with scopes_disabled():
        submission = SubmissionFactory()
        sub_question = QuestionFactory(
            event=submission.event, target=QuestionTarget.SUBMISSION
        )
        speaker_question = QuestionFactory(
            event=submission.event, target=QuestionTarget.SPEAKER
        )
        sub_answer = AnswerFactory(question=sub_question, submission=submission)
        AnswerFactory(question=speaker_question, submission=submission)
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission,
            context={"request": request, "questions": [sub_question, speaker_question]},
        )
        data = serializer.data

    assert data["answers"] == [sub_answer.pk]


@pytest.mark.django_db
def test_submission_serializer_get_answers_returns_empty_without_questions():
    with scopes_disabled():
        submission = SubmissionFactory()
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission, context={"request": request, "questions": []}
        )
        data = serializer.data

    assert data["answers"] == []


@pytest.mark.django_db
def test_submission_serializer_get_slots_filters_by_schedule():
    with scopes_disabled():
        submission = SubmissionFactory()
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        schedule = slot.schedule
        other_schedule = ScheduleFactory(event=submission.event)
        TalkSlotFactory(submission=submission, schedule=other_schedule, is_visible=True)
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission, context={"request": request, "schedule": schedule}
        )
        data = serializer.data

    assert data["slots"] == [slot.pk]


@pytest.mark.django_db
def test_submission_serializer_get_slots_returns_empty_without_schedule():
    with scopes_disabled():
        submission = SubmissionFactory()
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission, context={"request": request, "schedule": None}
        )
        data = serializer.data

    assert data["slots"] == []


@pytest.mark.parametrize(
    ("public_slots", "include_hidden"),
    ((True, False), (False, True)),
    ids=("public_only", "all_slots"),
)
@pytest.mark.django_db
def test_submission_serializer_get_slots_filters_by_visibility(
    public_slots, include_hidden
):
    with scopes_disabled():
        submission = SubmissionFactory()
        visible_slot = TalkSlotFactory(submission=submission, is_visible=True)
        hidden_slot = TalkSlotFactory(
            submission=submission, is_visible=False, schedule=visible_slot.schedule
        )
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission,
            context={
                "request": request,
                "schedule": visible_slot.schedule,
                "public_slots": public_slots,
            },
        )
        data = serializer.data

    expected = {visible_slot.pk}
    if include_hidden:
        expected.add(hidden_slot.pk)
    assert set(data["slots"]) == expected


@pytest.mark.parametrize(
    ("public_resources", "include_private"),
    ((True, False), (False, True)),
    ids=("public_only", "all_resources"),
)
@pytest.mark.django_db
def test_submission_serializer_get_resources_filters_by_visibility(
    public_resources, include_private
):
    with scopes_disabled():
        submission = SubmissionFactory()
        public_resource = ResourceFactory(
            submission=submission, link="https://example.com/public", is_public=True
        )
        private_resource = ResourceFactory(
            submission=submission, link="https://example.com/private", is_public=False
        )
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission,
            context={"request": request, "public_resources": public_resources},
        )
        data = serializer.data

    expected = {public_resource.pk}
    if include_private:
        expected.add(private_resource.pk)
    assert set(data["resources"]) == expected


@pytest.mark.django_db
def test_submission_serializer_get_resources_excludes_without_url():
    """Resources without a URL (no link and no file) are excluded."""
    with scopes_disabled():
        submission = SubmissionFactory()
        ResourceFactory(submission=submission, link="")
        request = make_api_request(submission.event)
        serializer = SubmissionSerializer(
            submission, context={"request": request, "public_resources": False}
        )
        data = serializer.data

    assert data["resources"] == []


@pytest.mark.django_db
def test_submission_orga_serializer_fields():
    with scopes_disabled():
        submission = SubmissionFactory()
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            submission, context={"request": request, "questions": [], "schedule": None}
        )
        data = serializer.data

    orga_keys = {
        "pending_state",
        "is_featured",
        "notes",
        "internal_notes",
        "invitation_token",
        "access_code",
        "review_code",
        "anonymised_data",
        "reviews",
        "assigned_reviewers",
        "is_anonymised",
        "median_score",
        "mean_score",
        "created",
        "updated",
        "invitations",
    }
    assert orga_keys <= set(data.keys())


@pytest.mark.django_db
def test_submission_orga_serializer_reviews_not_required():
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    assert serializer.fields["reviews"].required is False


@pytest.mark.django_db
def test_submission_orga_serializer_assigned_reviewers_queryset():
    """assigned_reviewers queryset is limited to the event's reviewers."""
    with scopes_disabled():
        event = EventFactory()
        team = Team.objects.create(
            organiser=event.organiser, name="Reviewers", is_reviewer=True
        )
        team.limit_events.add(event)
        reviewer = UserFactory()
        team.members.add(reviewer)
        UserFactory()  # non-reviewer user exists but must not appear in queryset
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    qs = serializer.fields["assigned_reviewers"].queryset
    assert set(qs) == {reviewer}


@pytest.mark.django_db
def test_submission_orga_serializer_validate_content_locale_valid():
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    result = serializer.validate_content_locale(event.locale)

    assert result == event.locale


@pytest.mark.django_db
def test_submission_orga_serializer_validate_content_locale_invalid():
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    with pytest.raises(ValidationError, match="Invalid locale"):
        serializer.validate_content_locale("xx")


@pytest.mark.django_db
def test_submission_orga_serializer_validate_slot_count_allows_one():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["present_multiple_times"] = False
        event.save()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    result = serializer.validate_slot_count(1)

    assert result == 1


@pytest.mark.django_db
def test_submission_orga_serializer_validate_slot_count_rejects_multiple_without_flag():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["present_multiple_times"] = False
        event.save()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    with pytest.raises(ValidationError, match="may only be 1"):
        serializer.validate_slot_count(3)


@pytest.mark.django_db
def test_submission_orga_serializer_validate_slot_count_allows_multiple_with_flag():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["present_multiple_times"] = True
        event.save()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})

    result = serializer.validate_slot_count(3)

    assert result == 3


@pytest.mark.django_db
def test_submission_orga_serializer_create_sets_event_and_defaults():
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})
        submission = serializer.create(
            {"title": "My Talk", "submission_type": event.cfp.default_type}
        )

    assert submission.event == event
    assert submission.content_locale == event.locale
    assert submission.title == "My Talk"


@pytest.mark.django_db
def test_submission_orga_serializer_create_converts_get_duration():
    """The 'get_duration' key (from DRF source mapping) is converted to 'duration'."""
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})
        submission = serializer.create(
            {
                "title": "My Talk",
                "submission_type": event.cfp.default_type,
                "get_duration": 45,
            }
        )

    assert submission.duration == 45


@pytest.mark.django_db
def test_submission_orga_serializer_create_with_tags():
    with scopes_disabled():
        event = EventFactory()
        tag = TagFactory(event=event)
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})
        submission = serializer.create(
            {
                "title": "Tagged Talk",
                "submission_type": event.cfp.default_type,
                "tags": [tag],
            }
        )
        assert list(submission.tags.all()) == [tag]


@pytest.mark.django_db
def test_submission_orga_serializer_update_basic():
    with scopes_disabled():
        submission = SubmissionFactory(title="Old Title")
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            instance=submission, context={"request": request}
        )
        updated = serializer.update(submission, {"title": "New Title"})

    assert updated.title == "New Title"


@pytest.mark.django_db
def test_submission_orga_serializer_update_with_tags():
    with scopes_disabled():
        submission = SubmissionFactory()
        tag = TagFactory(event=submission.event)
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            instance=submission, context={"request": request}
        )
        updated = serializer.update(submission, {"tags": [tag]})
        assert list(updated.tags.all()) == [tag]


@pytest.mark.django_db
def test_submission_orga_serializer_update_duration_change_updates_slot_end():
    """When duration changes via the serializer, scheduled slot end times are updated."""
    with scopes_disabled():
        submission = SubmissionFactory(duration=30)
        start = submission.event.datetime_from
        slot = TalkSlotFactory(
            submission=submission, start=start, end=start + dt.timedelta(minutes=30)
        )
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            instance=submission, context={"request": request}
        )

        serializer.update(submission, {"get_duration": 60})
        slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=60)


@pytest.mark.django_db
def test_submission_orga_serializer_update_slot_count_change_creates_slots():
    """When slot_count increases, new TalkSlot objects are created in the wip schedule."""
    with scopes_disabled():
        submission = SubmissionFactory(slot_count=1, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(submission=submission)
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            instance=submission, context={"request": request}
        )

        serializer.update(submission, {"slot_count": 2})

        slot_count = submission.event.wip_schedule.talks.filter(
            submission=submission
        ).count()
    assert slot_count == 2


@pytest.mark.django_db
def test_submission_orga_serializer_update_track_change_recalculates_review_scores():
    """When the track changes, review scores are recalculated because
    score_categories depend on the submission's track."""
    with scopes_disabled():
        submission = SubmissionFactory()
        track_a = TrackFactory(event=submission.event)
        track_b = TrackFactory(event=submission.event)
        submission.track = track_a
        submission.save()

        # Create a score category limited to track_a and a review with a score in it
        category = ReviewScoreCategoryFactory(event=submission.event)
        category.limit_tracks.add(track_a)
        review = ReviewFactory(submission=submission)
        score_obj = ReviewScoreFactory(category=category, value=5)
        review.scores.add(score_obj)
        review.save(update_score=True)
        review.refresh_from_db()
        assert review.score is not None
        original_updated = review.updated

        # Clear cached_property so the serializer sees fresh score_categories
        submission.__dict__.pop("score_categories", None)

        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            instance=submission, context={"request": request}
        )

        # Changing to track_b means the category limited to track_a no longer applies,
        # so update_review_scores should recalculate scores.
        serializer.update(submission, {"track": track_b})
        review.refresh_from_db()

    # The review was re-saved by update_review_scores
    assert review.updated > original_updated


@pytest.mark.django_db
def test_submission_orga_serializer_get_invitations():
    with scopes_disabled():
        submission = SubmissionFactory()
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="invited@example.com"
        )
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            submission, context={"request": request, "questions": [], "schedule": None}
        )
        data = serializer.data

    assert data["invitations"] == [invitation.pk]


@pytest.mark.django_db
def test_submission_orga_serializer_init_without_event():
    """When no event is on the request, assigned_reviewers queryset is not updated."""
    request = make_api_request(event=None)

    serializer = SubmissionOrgaSerializer(context={"request": request})

    assert serializer.event is None
    assert serializer.fields["reviews"].required is False


@pytest.mark.django_db
def test_submission_serializer_get_speakers_expanded():
    """When ?expand=speakers is passed, get_speakers returns serialized data."""
    with scopes_disabled():
        submission = SubmissionFactory()
        speaker = SpeakerFactory(event=submission.event)
        submission.speakers.add(speaker)
        request = make_api_request(event=submission.event, data={"expand": "speakers"})
        serializer = SubmissionSerializer(submission, context={"request": request})
        data = serializer.data

    assert len(data["speakers"]) == 1
    assert data["speakers"][0]["code"] == speaker.code
    assert data["speakers"][0]["name"] == speaker.user.name


@pytest.mark.django_db
def test_submission_serializer_get_answers_expanded():
    """When ?expand=answers is passed, get_answers returns serialized data."""
    with scopes_disabled():
        submission = SubmissionFactory()
        question = QuestionFactory(
            event=submission.event, target=QuestionTarget.SUBMISSION
        )
        answer = AnswerFactory(question=question, submission=submission)
        request = make_api_request(event=submission.event, data={"expand": "answers"})
        serializer = SubmissionSerializer(
            submission, context={"request": request, "questions": [question]}
        )
        data = serializer.data

    assert len(data["answers"]) == 1
    assert data["answers"][0]["id"] == answer.pk


@pytest.mark.django_db
def test_submission_serializer_get_slots_expanded():
    """When ?expand=slots is passed, get_slots returns serialized data."""
    with scopes_disabled():
        submission = SubmissionFactory()
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        request = make_api_request(event=submission.event, data={"expand": "slots"})
        serializer = SubmissionSerializer(
            submission, context={"request": request, "schedule": slot.schedule}
        )
        data = serializer.data

    assert len(data["slots"]) == 1
    assert data["slots"][0]["id"] == slot.pk


@pytest.mark.django_db
def test_submission_serializer_get_resources_expanded():
    """When ?expand=resources is passed, get_resources returns serialized data."""
    with scopes_disabled():
        submission = SubmissionFactory()
        resource = ResourceFactory(
            submission=submission, link="https://example.com/slides", is_public=True
        )
        request = make_api_request(event=submission.event, data={"expand": "resources"})
        serializer = SubmissionSerializer(submission, context={"request": request})
        data = serializer.data

    assert len(data["resources"]) == 1
    assert data["resources"][0]["id"] == resource.pk
    assert data["resources"][0]["resource"] == "https://example.com/slides"


@pytest.mark.django_db
def test_submission_orga_serializer_get_invitations_expanded():
    """When ?expand=invitations is passed, get_invitations returns serialized data."""
    with scopes_disabled():
        submission = SubmissionFactory()
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="expanded@example.com"
        )
        request = make_api_request(
            event=submission.event, data={"expand": "invitations"}
        )
        serializer = SubmissionOrgaSerializer(
            submission, context={"request": request, "questions": [], "schedule": None}
        )
        data = serializer.data

    assert len(data["invitations"]) == 1
    assert data["invitations"][0]["id"] == invitation.pk
    assert data["invitations"][0]["email"] == "expanded@example.com"


@pytest.mark.django_db
def test_submission_orga_serializer_create_with_image(make_image):
    """We use a real image via make_image because the serializer calls
    process_image(), which runs synchronously in tests (Celery eager mode)
    and requires a valid image file to succeed."""
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})
        submission = serializer.create(
            {
                "title": "Image Talk",
                "submission_type": event.cfp.default_type,
                "image": make_image("talk.png"),
            }
        )

    assert submission.image


@pytest.mark.django_db
def test_submission_orga_serializer_update_with_image(make_image):
    """We use a real image via make_image because the serializer calls
    process_image(), which runs synchronously in tests (Celery eager mode)
    and requires a valid image file to succeed."""
    with scopes_disabled():
        submission = SubmissionFactory()
        request = make_api_request(submission.event)
        serializer = SubmissionOrgaSerializer(
            instance=submission, context={"request": request}
        )
        updated = serializer.update(submission, {"image": make_image("new.png")})

    assert updated.image


@pytest.mark.django_db
def test_submission_orga_serializer_create_with_explicit_content_locale():
    """When content_locale is explicitly provided, the default is not applied."""
    with scopes_disabled():
        event = EventFactory()
        event.locale = "en"
        event.locales = ["en", "de"]
        event.save()
        request = make_api_request(event)
        serializer = SubmissionOrgaSerializer(context={"request": request})
        submission = serializer.create(
            {
                "title": "German Talk",
                "submission_type": event.cfp.default_type,
                "content_locale": "de",
            }
        )

    assert submission.content_locale == "de"
