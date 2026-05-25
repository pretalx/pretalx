# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from pretalx.api.serializers.submission import (
    AttendeeSignupSerializer,
    ResourceSerializer,
    ResourceWriteSerializer,
    SubmissionInvitationSerializer,
    SubmissionOrgaSerializer,
    SubmissionSerializer,
    SubmissionTypeSerializer,
    TagSerializer,
    TrackSerializer,
)
from pretalx.submission.domain.review import update_review_score
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import QuestionTarget, SubmissionStates
from tests.factories import (
    AnswerFactory,
    AttendeeSignupFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    ScheduleFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_resource_serializer_fields():
    resource = ResourceFactory()
    request = make_api_request(resource.submission.event)

    serializer = ResourceSerializer(resource, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {"id", "resource", "description", "is_public"}
    assert data["id"] == resource.pk
    assert data["is_public"] is True


def test_resource_serializer_get_resource_returns_url():
    resource = ResourceFactory(link="https://example.com/slides")
    request = make_api_request(resource.submission.event)

    serializer = ResourceSerializer(resource, context={"request": request})

    assert serializer.data["resource"] == "https://example.com/slides"


def test_resource_write_serializer_rejects_neither_link_nor_file():
    event = EventFactory()
    request = make_api_request(event)
    serializer = ResourceWriteSerializer(
        data={"description": "d", "link": ""}, context={"request": request}
    )

    assert not serializer.is_valid()
    assert "provide a link or upload a file" in str(serializer.errors)


def test_resource_write_serializer_rejects_both_link_and_file():
    submission = SubmissionFactory()
    request = make_api_request(submission.event)
    # An instance with a file already attached + new link on top: hits the
    # "both" branch of Resource.clean() without needing CachedFile + auth setup
    # that UploadedFileField.to_internal_value would demand.
    instance = ResourceFactory(submission=submission, link="")
    instance.resource = SimpleUploadedFile("f.pdf", b"x")
    serializer = ResourceWriteSerializer(
        instance=instance, context={"request": request}
    )

    with pytest.raises(ValidationError, match="cannot do both"):
        serializer._run_model_full_clean(
            {"link": "https://example.com", "description": "d"}
        )


def test_resource_write_serializer_accepts_link_only():
    event = EventFactory()
    request = make_api_request(event)
    serializer = ResourceWriteSerializer(
        data={"link": "https://example.com", "description": "slides"},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize(
    ("extra_data", "expected_link"),
    (({"link": "https://example.com/slides"}, "https://example.com/slides"), ({}, "")),
    ids=("with_link", "without_link"),
)
def test_resource_write_serializer_create_link_handling(extra_data, expected_link):
    submission = SubmissionFactory()
    request = make_api_request(submission.event)
    serializer = ResourceWriteSerializer(context={"request": request})

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


def test_tag_serializer_fields():
    tag = TagFactory()
    request = make_api_request(tag.event)

    serializer = TagSerializer(tag, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {"id", "tag", "description", "color", "is_public"}
    assert data["id"] == tag.pk
    assert data["color"] == tag.color


def test_tag_serializer_create_sets_event():
    event = EventFactory()
    request = make_api_request(event)
    serializer = TagSerializer(
        data={"tag": "python", "color": "#00ff00", "is_public": True},
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    tag = serializer.save()

    assert tag.event == event


def test_tag_serializer_rejects_duplicate():
    existing = TagFactory(tag="python")
    request = make_api_request(existing.event)
    serializer = TagSerializer(
        data={"tag": "python", "color": "#00ff00", "is_public": False},
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "tag" in serializer.errors


def test_tag_serializer_allows_editing_own():
    tag = TagFactory(tag="python")
    request = make_api_request(tag.event)
    serializer = TagSerializer(
        instance=tag,
        data={"tag": "python", "color": tag.color, "is_public": tag.is_public},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


def test_tag_serializer_rejects_duplicate_when_editing_other():
    event = EventFactory()
    TagFactory(event=event, tag="python")
    other = TagFactory(event=event, tag="django")
    request = make_api_request(event)
    serializer = TagSerializer(
        instance=other,
        data={"tag": "python", "color": other.color, "is_public": other.is_public},
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "tag" in serializer.errors


def test_tag_serializer_accepts_unique():
    event = EventFactory()
    TagFactory(event=event, tag="python")
    request = make_api_request(event)
    serializer = TagSerializer(
        data={"tag": "django", "color": "#0000ff", "is_public": False},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


def test_submission_type_serializer_fields():
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
        "attendee_signup_required",
    }
    assert data["id"] == stype.pk
    assert data["default_duration"] == stype.default_duration


def test_submission_type_serializer_create_sets_event():
    event = EventFactory()
    request = make_api_request(event)
    serializer = SubmissionTypeSerializer(
        data={"name": "Workshop", "default_duration": 90}, context={"request": request}
    )
    assert serializer.is_valid(), serializer.errors
    stype = serializer.save()

    assert stype.event == event


def test_submission_type_serializer_rejects_duplicate_name():
    event = EventFactory()
    SubmissionTypeFactory(event=event, name="Workshop")
    request = make_api_request(event)
    serializer = SubmissionTypeSerializer(
        data={"name": "Workshop", "default_duration": 90}, context={"request": request}
    )

    assert not serializer.is_valid()
    assert "name" in serializer.errors


def test_submission_type_serializer_allows_editing_own_name():
    stype = SubmissionTypeFactory(name="Workshop")
    request = make_api_request(stype.event)
    serializer = SubmissionTypeSerializer(
        instance=stype,
        data={"name": "Workshop", "default_duration": stype.default_duration},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


def test_submission_type_serializer_rejects_duplicate_name_when_editing_other():
    event = EventFactory()
    SubmissionTypeFactory(event=event, name="Workshop")
    other = SubmissionTypeFactory(event=event, name="Lightning")
    request = make_api_request(event)
    serializer = SubmissionTypeSerializer(
        instance=other,
        data={"name": "Workshop", "default_duration": other.default_duration},
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "name" in serializer.errors


def test_submission_type_serializer_update_propagates_duration_to_slots():
    """When default_duration changes, slot end times are updated for submissions
    that inherit their duration from the type (duration=None)."""
    stype = SubmissionTypeFactory(default_duration=30)
    submission = SubmissionFactory(event=stype.event, submission_type=stype)
    start = submission.event.datetime_from
    slot = TalkSlotFactory(
        submission=submission, start=start, end=start + dt.timedelta(minutes=30)
    )
    request = make_api_request(stype.event)
    serializer = SubmissionTypeSerializer(instance=stype, context={"request": request})

    serializer.update(stype, {"default_duration": 60})
    slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=60)


def test_submission_type_serializer_update_skips_update_duration_when_unchanged():
    """When default_duration stays the same, slot end times are not modified."""
    stype = SubmissionTypeFactory(default_duration=30)
    submission = SubmissionFactory(event=stype.event, submission_type=stype)
    start = submission.event.datetime_from
    slot = TalkSlotFactory(
        submission=submission, start=start, end=start + dt.timedelta(minutes=30)
    )
    request = make_api_request(stype.event)
    serializer = SubmissionTypeSerializer(instance=stype, context={"request": request})

    serializer.update(stype, {"default_duration": 30})
    slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=30)


def test_track_serializer_fields():
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
        "attendee_signup_required",
    }
    assert data["id"] == track.pk
    assert data["color"] == track.color


def test_track_serializer_create_sets_event():
    event = EventFactory()
    request = make_api_request(event)
    serializer = TrackSerializer(
        data={"name": "Security", "color": "#ff0000", "position": 0},
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    track = serializer.save()

    assert track.event == event


def test_track_serializer_rejects_duplicate_name():
    track = TrackFactory(name="Security")
    request = make_api_request(track.event)
    serializer = TrackSerializer(
        data={"name": "Security", "color": "#00ff00"}, context={"request": request}
    )

    assert not serializer.is_valid()
    assert "name" in serializer.errors


def test_track_serializer_allows_editing_own_name():
    track = TrackFactory(name="Security")
    request = make_api_request(track.event)
    serializer = TrackSerializer(
        instance=track,
        data={"name": "Security", "color": track.color},
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


def test_track_serializer_rejects_duplicate_name_when_editing_other():
    event = EventFactory()
    TrackFactory(event=event, name="Security")
    other = TrackFactory(event=event, name="DevOps")
    request = make_api_request(event)
    serializer = TrackSerializer(
        instance=other,
        data={"name": "Security", "color": other.color},
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "name" in serializer.errors


def test_submission_invitation_serializer_fields():
    submission = SubmissionFactory()
    invitation = SubmissionInvitationFactory(
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


def test_submission_serializer_init_sets_querysets():
    event = EventFactory(feature_flags={"use_tracks": True})
    stype = event.cfp.default_type
    track = TrackFactory(event=event)
    tag = TagFactory(event=event)
    request = make_api_request(event)
    serializer = SubmissionSerializer(context={"request": request})

    assert list(serializer.fields["submission_type"].queryset) == [stype]
    assert list(serializer.fields["track"].queryset) == [track]
    assert list(serializer.fields["tags"].child_relation.queryset) == [tag]


def test_submission_serializer_init_removes_track_when_feature_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})
    request = make_api_request(event)
    serializer = SubmissionSerializer(context={"request": request})

    assert "track" not in serializer.fields


def test_submission_serializer_init_removes_unrequested_cfp_fields():
    event = EventFactory(cfp__fields={"description": {"visibility": "do_not_ask"}})
    request = make_api_request(event)
    serializer = SubmissionSerializer(context={"request": request})

    assert "description" not in serializer.fields


def test_submission_serializer_init_sets_field_required_from_cfp():
    event = EventFactory(
        cfp__fields={
            "abstract": {"visibility": "required"},
            "description": {"visibility": "optional"},
        }
    )
    request = make_api_request(event)
    serializer = SubmissionSerializer(context={"request": request})

    assert serializer.fields["abstract"].required is True
    assert serializer.fields["description"].required is False


def test_submission_serializer_init_without_event():
    request = make_api_request(event=None)

    serializer = SubmissionSerializer(context={"request": request})

    assert serializer.event is None


def test_submission_serializer_fields():
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
        "attendee_signup_required",
        "attendee_signup_capacity",
        "content_locale",
        "do_not_record",
        "resources",
        "slots",
        "answers",
    }
    assert expected_keys <= set(data.keys())
    assert data["code"] == submission.code
    assert data["title"] == str(submission.title)


def test_submission_serializer_get_speakers_returns_codes():
    role = SpeakerRoleFactory()
    submission = role.submission
    speaker = role.speaker
    request = make_api_request(submission.event)
    serializer = SubmissionSerializer(submission, context={"request": request})
    data = serializer.data

    assert data["speakers"] == [speaker.code]


def test_submission_serializer_get_answers_filters_by_submission_questions():
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


def test_submission_serializer_get_answers_returns_empty_without_questions():
    submission = SubmissionFactory()
    request = make_api_request(submission.event)
    serializer = SubmissionSerializer(
        submission, context={"request": request, "questions": []}
    )
    data = serializer.data

    assert data["answers"] == []


def test_submission_serializer_get_slots_filters_by_schedule():
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


def test_submission_serializer_get_slots_returns_empty_without_schedule():
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
def test_submission_serializer_get_slots_filters_by_visibility(
    public_slots, include_hidden
):
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
def test_submission_serializer_get_resources_filters_by_visibility(
    public_resources, include_private
):
    submission = SubmissionFactory()
    public_resource = ResourceFactory(
        submission=submission, link="https://example.com/public", is_public=True
    )
    private_resource = ResourceFactory(
        submission=submission, link="https://example.com/private", is_public=False
    )
    request = make_api_request(submission.event)
    serializer = SubmissionSerializer(
        submission, context={"request": request, "public_resources": public_resources}
    )
    data = serializer.data

    expected = {public_resource.pk}
    if include_private:
        expected.add(private_resource.pk)
    assert set(data["resources"]) == expected


def test_submission_serializer_get_resources_excludes_without_url():
    submission = SubmissionFactory()
    ResourceFactory(submission=submission, link="")
    request = make_api_request(submission.event)
    serializer = SubmissionSerializer(
        submission, context={"request": request, "public_resources": False}
    )
    data = serializer.data

    assert data["resources"] == []


def test_submission_orga_serializer_fields():
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


def test_submission_orga_serializer_assigned_reviewers_queryset():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, name="Reviewers", is_reviewer=True)
    team.limit_events.add(event)
    reviewer = UserFactory()
    team.members.add(reviewer)
    UserFactory()  # non-reviewer user exists but must not appear in queryset
    request = make_api_request(event)
    serializer = SubmissionOrgaSerializer(context={"request": request})

    qs = serializer.fields["assigned_reviewers"].child_relation.queryset
    assert set(qs) == {reviewer}


def test_submission_orga_serializer_content_locale_choices():
    event = EventFactory()
    request = make_api_request(event)
    serializer = SubmissionOrgaSerializer(context={"request": request})

    choices = dict(serializer.fields["content_locale"].choices)
    assert set(choices.keys()) == set(event.content_locales)


def test_submission_orga_serializer_rejects_invalid_content_locale():
    event = EventFactory()
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": "xx",
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "content_locale" in serializer.errors


def test_submission_orga_serializer_allows_slot_count_one():
    event = EventFactory(feature_flags={"present_multiple_times": False})
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": event.locale,
            "slot_count": 1,
        },
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


def test_submission_orga_serializer_rejects_slot_count_without_flag():
    event = EventFactory(feature_flags={"present_multiple_times": False})
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": event.locale,
            "slot_count": 3,
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "slot_count" in serializer.errors
    assert "may only be 1" in str(serializer.errors["slot_count"])


def test_submission_orga_serializer_allows_multiple_slots_with_flag():
    event = EventFactory(feature_flags={"present_multiple_times": True})
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": event.locale,
            "slot_count": 3,
        },
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors


def test_submission_orga_serializer_create_sets_event_and_defaults():
    event = EventFactory()
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "My Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": event.locale,
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    submission = serializer.save()

    assert submission.event == event
    assert submission.content_locale == event.locale
    assert submission.title == "My Talk"


def test_submission_orga_serializer_create_with_assigned_reviewers():
    event = EventFactory()
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(reviewer)
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "My Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": event.locale,
            "assigned_reviewers": [reviewer.code],
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    submission = serializer.save()

    assert list(submission.assigned_reviewers.all()) == [reviewer]


def test_submission_orga_serializer_init_skips_content_locale_when_not_requested():
    event = EventFactory(cfp__fields={"content_locale": {"visibility": "do_not_ask"}})
    request = make_api_request(event)
    serializer = SubmissionOrgaSerializer(context={"request": request})

    assert "content_locale" not in serializer.fields


def test_submission_orga_serializer_create_converts_get_duration():
    event = EventFactory()
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "My Talk",
            "submission_type": event.cfp.default_type.pk,
            "duration": 45,
            "abstract": "An abstract",
            "content_locale": event.locale,
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    submission = serializer.save()

    assert submission.duration == 45


def test_submission_orga_serializer_create_with_tags():
    event = EventFactory()
    tag = TagFactory(event=event)
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "Tagged Talk",
            "submission_type": event.cfp.default_type.pk,
            "tags": [tag.pk],
            "abstract": "An abstract",
            "content_locale": event.locale,
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    submission = serializer.save()
    assert list(submission.tags.all()) == [tag]


def test_submission_orga_serializer_update_basic():
    submission = SubmissionFactory(title="Old Title")
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission, context={"request": request}
    )
    updated = serializer.update(submission, {"title": "New Title"})

    assert updated.title == "New Title"


def test_submission_orga_serializer_update_with_tags():
    submission = SubmissionFactory()
    tag = TagFactory(event=submission.event)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission, context={"request": request}
    )
    updated = serializer.update(submission, {"tags": [tag]})
    assert list(updated.tags.all()) == [tag]


def test_submission_orga_serializer_update_validates_tag_pks():
    submission = SubmissionFactory()
    tag1 = TagFactory(event=submission.event)
    tag2 = TagFactory(event=submission.event)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"tags": [tag1.pk, tag2.pk]},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert set(submission.tags.all()) == {tag1, tag2}


def test_submission_orga_serializer_update_rejects_cross_event_tag():
    submission = SubmissionFactory()
    other_event = EventFactory()
    foreign_tag = TagFactory(event=other_event)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"tags": [foreign_tag.pk]},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "tags" in serializer.errors


def test_submission_orga_serializer_update_validates_assigned_reviewer_codes():
    submission = SubmissionFactory()
    reviewer = UserFactory()
    team = TeamFactory(
        organiser=submission.event.organiser, all_events=True, is_reviewer=True
    )
    team.members.add(reviewer)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"assigned_reviewers": [reviewer.code]},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert list(submission.assigned_reviewers.all()) == [reviewer]


def test_submission_orga_serializer_update_empty_tags_clears():
    submission = SubmissionFactory()
    tag = TagFactory(event=submission.event)
    submission.tags.add(tag)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"tags": []},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert list(submission.tags.all()) == []


def test_submission_orga_serializer_update_omitted_tags_unchanged():
    submission = SubmissionFactory()
    tag = TagFactory(event=submission.event)
    submission.tags.add(tag)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"title": "Changed"},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert list(submission.tags.all()) == [tag]


def test_submission_orga_serializer_update_null_tags_rejected():
    submission = SubmissionFactory()
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"tags": None},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "tags" in serializer.errors


def test_submission_orga_serializer_update_empty_assigned_reviewers_clears():
    submission = SubmissionFactory()
    reviewer = UserFactory()
    team = TeamFactory(
        organiser=submission.event.organiser, all_events=True, is_reviewer=True
    )
    team.members.add(reviewer)
    submission.assigned_reviewers.add(reviewer)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"assigned_reviewers": []},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert list(submission.assigned_reviewers.all()) == []


def test_submission_orga_serializer_update_duration_change_updates_slot_end():
    """When duration changes via the serializer, scheduled slot end times are updated."""
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


def test_submission_orga_serializer_update_slot_count_change_creates_slots():
    """When slot_count increases, new TalkSlot objects are created in the wip schedule."""
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


def test_submission_orga_serializer_update_track_change_recalculates_review_scores():
    """When the track changes, review scores are recalculated because
    score_categories depend on the submission's track."""
    event = EventFactory()
    track_a = TrackFactory(event=event)
    track_b = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track_a)

    # Create a score category limited to track_a and a review with a score in it
    category = ReviewScoreCategoryFactory(event=submission.event)
    category.limit_tracks.add(track_a)
    review = ReviewFactory(submission=submission)
    score_obj = ReviewScoreFactory(category=category, value=5)
    review.scores.add(score_obj)
    update_review_score(review)
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


def test_submission_orga_serializer_get_invitations():
    submission = SubmissionFactory()
    invitation = SubmissionInvitationFactory(
        submission=submission, email="invited@example.com"
    )
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        submission, context={"request": request, "questions": [], "schedule": None}
    )
    data = serializer.data

    assert data["invitations"] == [invitation.pk]


def test_submission_orga_serializer_init_without_event():
    request = make_api_request(event=None)

    serializer = SubmissionOrgaSerializer(context={"request": request})

    assert serializer.event is None
    assert serializer.fields["reviews"].required is False


def test_submission_serializer_get_speakers_expanded():
    role = SpeakerRoleFactory()
    submission = role.submission
    speaker = role.speaker
    request = make_api_request(event=submission.event, data={"expand": "speakers"})
    serializer = SubmissionSerializer(submission, context={"request": request})
    data = serializer.data

    assert len(data["speakers"]) == 1
    assert data["speakers"][0]["code"] == speaker.code
    assert data["speakers"][0]["name"] == speaker.user.name


def test_submission_serializer_get_answers_expanded():
    submission = SubmissionFactory()
    question = QuestionFactory(event=submission.event, target=QuestionTarget.SUBMISSION)
    answer = AnswerFactory(question=question, submission=submission)
    request = make_api_request(event=submission.event, data={"expand": "answers"})
    serializer = SubmissionSerializer(
        submission, context={"request": request, "questions": [question]}
    )
    data = serializer.data

    assert len(data["answers"]) == 1
    assert data["answers"][0]["id"] == answer.pk


def test_submission_serializer_get_slots_expanded():
    submission = SubmissionFactory()
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    request = make_api_request(event=submission.event, data={"expand": "slots"})
    serializer = SubmissionSerializer(
        submission, context={"request": request, "schedule": slot.schedule}
    )
    data = serializer.data

    assert len(data["slots"]) == 1
    assert data["slots"][0]["id"] == slot.pk


def test_submission_serializer_get_resources_expanded():
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


def test_submission_orga_serializer_get_invitations_expanded():
    submission = SubmissionFactory()
    invitation = SubmissionInvitationFactory(
        submission=submission, email="expanded@example.com"
    )
    request = make_api_request(event=submission.event, data={"expand": "invitations"})
    serializer = SubmissionOrgaSerializer(
        submission, context={"request": request, "questions": [], "schedule": None}
    )
    data = serializer.data

    assert len(data["invitations"]) == 1
    assert data["invitations"][0]["id"] == invitation.pk
    assert data["invitations"][0]["email"] == "expanded@example.com"


def test_submission_orga_serializer_update_with_image(make_image):
    """We use a real image via make_image because the serializer calls
    process_image(), which runs synchronously in tests (Celery eager mode)
    and requires a valid image file to succeed."""
    submission = SubmissionFactory()
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission, context={"request": request}
    )
    updated = serializer.update(submission, {"image": make_image("new.png")})

    assert updated.image


def test_submission_orga_serializer_create_with_explicit_content_locale():
    event = EventFactory(locale="en", content_locale_array="en,de")
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "German Talk",
            "submission_type": event.cfp.default_type.pk,
            "content_locale": "de",
            "abstract": "Ein Abstract",
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    submission = serializer.save()

    assert submission.content_locale == "de"


def test_submission_orga_serializer_create_defaults_content_locale_to_event():
    """When ``content_locale`` is missing from validated data, ``create``
    falls back to the event's primary locale rather than leaving it blank.

    We call ``create`` directly rather than via ``is_valid``/``save`` because
    the serializer's required-field machinery would otherwise inject the
    event default before reaching this branch.
    """
    event = EventFactory(locale="de", content_locale_array="en,de")
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(context={"request": request})

    submission = serializer.create(
        {
            "event": event,
            "title": "Untitled",
            "submission_type": event.cfp.default_type,
            "abstract": "An abstract",
        }
    )

    assert submission.content_locale == "de"


def test_submission_orga_serializer_create_with_image(make_image):
    """``create`` routes uploaded images through ``submission.image.save``
    so the upload lands on the submission's hashed ``upload_to`` path
    (``{event.slug}/submissions/{code}/image_<random>.png``)."""
    event = EventFactory()
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(context={"request": request})

    submission = serializer.create(
        {
            "event": event,
            "title": "Illustrated Talk",
            "submission_type": event.cfp.default_type,
            "abstract": "An abstract",
            "content_locale": event.locale,
            "image": make_image("created.png"),
        }
    )

    assert submission.image
    assert submission.image.name.startswith(
        f"{event.slug}/submissions/{submission.code}/image_"
    )
    assert submission.image.name.endswith(".png")


def test_attendee_signup_serializer_fields():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    signup = AttendeeSignupFactory(
        submission=submission, state=AttendeeSignupStates.CANCELED
    )

    data = AttendeeSignupSerializer(signup).data

    assert set(data.keys()) == {
        "id",
        "name",
        "email",
        "state",
        "position",
        "created",
        "updated",
    }
    assert data["name"] == signup.attendee.user.name
    assert data["email"] == signup.attendee.user.email
    assert data["state"] == AttendeeSignupStates.CANCELED
    assert data["position"] == 0
