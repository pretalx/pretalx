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


def test_resource_serializer_data():
    resource = ResourceFactory(link="https://example.com/slides")
    request = make_api_request(resource.submission.event)

    serializer = ResourceSerializer(resource, context={"request": request})

    assert serializer.data == {
        "id": resource.pk,
        "resource": "https://example.com/slides",
        "description": resource.description,
        "is_public": True,
    }


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        ({"link": "https://example.com", "description": "slides"}, {}),
        (
            {"description": "d", "link": ""},
            {"__all__": ["Please provide a link or upload a file!"]},
        ),
    ),
    ids=("link_only", "neither_link_nor_file"),
)
def test_resource_write_serializer_requires_link_or_file(data, errors):
    event = EventFactory()
    request = make_api_request(event)
    serializer = ResourceWriteSerializer(data=data, context={"request": request})

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


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
    TagFactory(event=event, tag="python")
    request = make_api_request(event)
    serializer = TagSerializer(
        data={"tag": "django", "color": "#00ff00", "is_public": True},
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    tag = serializer.save()

    assert tag.event == event
    assert tag.tag == "django"


def test_tag_serializer_rejects_duplicate():
    existing = TagFactory(tag="python")
    request = make_api_request(existing.event)
    serializer = TagSerializer(
        data={"tag": "python", "color": "#00ff00", "is_public": False},
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert serializer.errors == {"tag": ["You already have a tag by this name!"]}


@pytest.mark.parametrize(
    ("name", "errors"),
    (("django", {}), ("python", {"tag": ["You already have a tag by this name!"]})),
    ids=("own_name", "other_name"),
)
def test_tag_serializer_edit_rejects_only_other_tags_name(name, errors):
    event = EventFactory()
    TagFactory(event=event, tag="python")
    tag = TagFactory(event=event, tag="django")
    request = make_api_request(event)
    serializer = TagSerializer(
        instance=tag,
        data={"tag": name, "color": tag.color, "is_public": tag.is_public},
        context={"request": request},
    )

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


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
    assert serializer.errors == {
        "name": ["You already have a session type by this name!"]
    }


@pytest.mark.parametrize(
    ("name", "errors"),
    (
        ("Lightning", {}),
        ("Workshop", {"name": ["You already have a session type by this name!"]}),
    ),
    ids=("own_name", "other_name"),
)
def test_submission_type_serializer_edit_rejects_only_other_types_name(name, errors):
    event = EventFactory()
    SubmissionTypeFactory(event=event, name="Workshop")
    stype = SubmissionTypeFactory(event=event, name="Lightning")
    request = make_api_request(event)
    serializer = SubmissionTypeSerializer(
        instance=stype,
        data={"name": name, "default_duration": stype.default_duration},
        context={"request": request},
    )

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


@pytest.mark.parametrize(
    ("new_duration", "expected_minutes"),
    ((60, 60), (30, 30)),
    ids=("changed", "unchanged"),
)
def test_submission_type_serializer_update_propagates_duration_to_slots(
    new_duration, expected_minutes
):
    stype = SubmissionTypeFactory(default_duration=30)
    submission = SubmissionFactory(event=stype.event, submission_type=stype)
    start = submission.event.datetime_from
    slot = TalkSlotFactory(
        submission=submission, start=start, end=start + dt.timedelta(minutes=30)
    )
    request = make_api_request(stype.event)
    serializer = SubmissionTypeSerializer(instance=stype, context={"request": request})

    serializer.update(stype, {"default_duration": new_duration})
    slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=expected_minutes)


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
    assert serializer.errors == {"name": ["You already have a track by this name!"]}


@pytest.mark.parametrize(
    ("name", "errors"),
    (
        ("DevOps", {}),
        ("Security", {"name": ["You already have a track by this name!"]}),
    ),
    ids=("own_name", "other_name"),
)
def test_track_serializer_edit_rejects_only_other_tracks_name(name, errors):
    event = EventFactory()
    TrackFactory(event=event, name="Security")
    track = TrackFactory(event=event, name="DevOps")
    request = make_api_request(event)
    serializer = TrackSerializer(
        instance=track,
        data={"name": name, "color": track.color},
        context={"request": request},
    )

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


def test_submission_serializer_init_sets_querysets():
    event = EventFactory(feature_flags={"use_tracks": True})
    stype = event.cfp.default_type
    track = TrackFactory(event=event)
    request = make_api_request(event)
    serializer = SubmissionSerializer(context={"request": request})

    assert list(serializer.fields["submission_type"].queryset) == [stype]
    assert list(serializer.fields["track"].queryset) == [track]


def test_submission_orga_serializer_init_sets_querysets_and_choices():
    event = EventFactory()
    tag = TagFactory(event=event)
    TagFactory()
    team = TeamFactory(organiser=event.organiser, name="Reviewers", is_reviewer=True)
    team.limit_events.add(event)
    reviewer = UserFactory()
    team.members.add(reviewer)
    UserFactory()
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(context={"request": request})

    assert list(serializer.fields["tags"].child_relation.queryset) == [tag]
    assert set(serializer.fields["assigned_reviewers"].child_relation.queryset) == {
        reviewer
    }
    assert set(dict(serializer.fields["content_locale"].choices)) == set(
        event.content_locales
    )


@pytest.mark.parametrize(
    ("public_tags", "expect_internal_tag"), ((True, False), (False, True))
)
def test_submission_serializer_get_tags_filters_by_visibility(
    public_tags, expect_internal_tag
):
    submission = SubmissionFactory()
    public_tag = TagFactory(event=submission.event, is_public=True)
    internal_tag = TagFactory(event=submission.event, is_public=False)
    submission.tags.add(public_tag, internal_tag)
    request = make_api_request(submission.event)
    serializer = SubmissionSerializer(
        submission, context={"request": request, "public_tags": public_tags}
    )

    expected = (
        [public_tag.pk, internal_tag.pk] if expect_internal_tag else [public_tag.pk]
    )
    assert sorted(serializer.data["tags"]) == sorted(expected)


@pytest.mark.parametrize(
    ("event_kwargs", "expected"),
    (
        (
            {
                "feature_flags": {"use_tracks": False},
                "cfp__fields": {
                    "abstract": {"visibility": "required"},
                    "description": {"visibility": "optional"},
                },
            },
            {"abstract": True, "description": False},
        ),
        (
            {
                "feature_flags": {"use_tracks": True},
                "cfp__fields": {
                    "abstract": {"visibility": "required"},
                    "description": {"visibility": "do_not_ask"},
                },
            },
            {"track": False, "abstract": True},
        ),
    ),
    ids=("no_tracks_optional_description", "tracks_no_description"),
)
def test_submission_serializer_init_fields_follow_event_and_cfp(event_kwargs, expected):
    event = EventFactory(**event_kwargs)
    request = make_api_request(event)
    serializer = SubmissionSerializer(context={"request": request})

    assert {
        name: field.required
        for name, field in serializer.fields.items()
        if name in ("track", "abstract", "description")
    } == expected


def test_submission_serializer_fields():
    submission = SubmissionFactory()
    request = make_api_request(submission.event)
    base = SubmissionSerializer(
        submission, context={"request": request, "questions": [], "schedule": None}
    ).data
    orga = SubmissionOrgaSerializer(
        submission, context={"request": request, "questions": [], "schedule": None}
    ).data

    assert set(base.keys()) == {
        "code",
        "title",
        "speakers",
        "submission_type",
        "track",
        "tags",
        "state",
        "abstract",
        "description",
        "duration",
        "slot_count",
        "attendee_signup_required",
        "attendee_signup_capacity",
        "signup_status",
        "content_locale",
        "do_not_record",
        "image",
        "resources",
        "slots",
        "answers",
    }
    assert set(orga.keys()) - set(base.keys()) == {
        "pending_state",
        "is_featured",
        "notes",
        "internal_notes",
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
    assert base["code"] == submission.code
    assert base["title"] == str(submission.title)
    assert base["answers"] == []
    assert base["slots"] == []


def test_submission_serializer_get_speakers_codes_and_expanded():
    role = SpeakerRoleFactory()
    submission = role.submission
    speaker = role.speaker
    event = submission.event

    codes = SubmissionSerializer(
        submission, context={"request": make_api_request(event)}
    ).data["speakers"]
    expanded = SubmissionSerializer(
        submission,
        context={"request": make_api_request(event, data={"expand": "speakers"})},
    ).data["speakers"]

    assert codes == [speaker.code]
    assert [(s["code"], s["name"]) for s in expanded] == [
        (speaker.code, speaker.user.name)
    ]


def test_submission_serializer_get_answers_filters_by_submission_questions():
    submission = SubmissionFactory()
    event = submission.event
    sub_question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    speaker_question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    sub_answer = AnswerFactory(question=sub_question, submission=submission)
    AnswerFactory(question=speaker_question, submission=submission)
    questions = [sub_question, speaker_question]

    pks = SubmissionSerializer(
        submission, context={"request": make_api_request(event), "questions": questions}
    ).data["answers"]
    expanded = SubmissionSerializer(
        submission,
        context={
            "request": make_api_request(event, data={"expand": "answers"}),
            "questions": questions,
        },
    ).data["answers"]

    assert pks == [sub_answer.pk]
    assert [answer["id"] for answer in expanded] == [sub_answer.pk]


@pytest.mark.parametrize(
    ("public_slots", "include_hidden"),
    ((True, False), (False, True)),
    ids=("public_only", "all_slots"),
)
def test_submission_serializer_get_slots_filters_by_schedule_and_visibility(
    public_slots, include_hidden
):
    submission = SubmissionFactory()
    event = submission.event
    visible_slot = TalkSlotFactory(submission=submission, is_visible=True)
    hidden_slot = TalkSlotFactory(
        submission=submission, is_visible=False, schedule=visible_slot.schedule
    )
    TalkSlotFactory(
        submission=submission, schedule=ScheduleFactory(event=event), is_visible=True
    )
    context = {"schedule": visible_slot.schedule, "public_slots": public_slots}

    pks = SubmissionSerializer(
        submission, context={"request": make_api_request(event), **context}
    ).data["slots"]
    expanded = SubmissionSerializer(
        submission,
        context={
            "request": make_api_request(event, data={"expand": "slots"}),
            **context,
        },
    ).data["slots"]

    expected = {visible_slot.pk}
    if include_hidden:
        expected.add(hidden_slot.pk)
    assert set(pks) == expected
    assert {slot["id"] for slot in expanded} == expected


@pytest.mark.parametrize(
    ("public_resources", "include_private"),
    ((True, False), (False, True)),
    ids=("public_only", "all_resources"),
)
def test_submission_serializer_get_resources_filters_by_visibility_and_url(
    public_resources, include_private
):
    submission = SubmissionFactory()
    event = submission.event
    public_resource = ResourceFactory(
        submission=submission, link="https://example.com/public", is_public=True
    )
    private_resource = ResourceFactory(
        submission=submission, link="https://example.com/private", is_public=False
    )
    ResourceFactory(submission=submission, link="", is_public=True)
    context = {"public_resources": public_resources}

    pks = SubmissionSerializer(
        submission, context={"request": make_api_request(event), **context}
    ).data["resources"]
    expanded = SubmissionSerializer(
        submission,
        context={
            "request": make_api_request(event, data={"expand": "resources"}),
            **context,
        },
    ).data["resources"]

    expected = {public_resource.pk}
    if include_private:
        expected.add(private_resource.pk)
    assert set(pks) == expected
    assert {(r["id"], r["resource"]) for r in expanded} == {
        (r.pk, r.link) for r in (public_resource, private_resource) if r.pk in expected
    }


def test_submission_invitation_serializer_data_and_orga_invitations():
    submission = SubmissionFactory()
    event = submission.event
    invitation = SubmissionInvitationFactory(
        submission=submission, email="invited@example.com"
    )
    context = {"questions": [], "schedule": None}

    invitation_data = SubmissionInvitationSerializer(
        invitation, context={"request": make_api_request(event)}
    ).data
    pks = SubmissionOrgaSerializer(
        submission, context={"request": make_api_request(event), **context}
    ).data["invitations"]
    expanded = SubmissionOrgaSerializer(
        submission,
        context={
            "request": make_api_request(event, data={"expand": "invitations"}),
            **context,
        },
    ).data["invitations"]

    assert set(invitation_data.keys()) == {"id", "email", "created", "updated"}
    assert invitation_data["id"] == invitation.pk
    assert invitation_data["email"] == "invited@example.com"
    assert pks == [invitation.pk]
    assert expanded == [invitation_data]


@pytest.mark.parametrize(
    ("present_multiple_times", "extra_data", "errors"),
    (
        (False, {"slot_count": 1}, {}),
        (
            False,
            {"slot_count": 3},
            {"slot_count": ["Slot count may only be 1 in this event."]},
        ),
        (True, {"slot_count": 3}, {}),
        (
            False,
            {"content_locale": "xx"},
            {"content_locale": ['"xx" is not a valid choice.']},
        ),
    ),
    ids=("one_slot", "multiple_slots_without_flag", "multiple_slots", "bad_locale"),
)
def test_submission_orga_serializer_validates_slot_count_and_content_locale(
    present_multiple_times, extra_data, errors
):
    event = EventFactory(
        feature_flags={"present_multiple_times": present_multiple_times}
    )
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "An abstract",
            "content_locale": event.locale,
            **extra_data,
        },
        context={"request": request},
    )

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


def test_submission_orga_serializer_create_from_data():
    event = EventFactory(locale="en", content_locales=["en", "de"])
    tag = TagFactory(event=event)
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(reviewer)
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(
        data={
            "title": "German Talk",
            "submission_type": event.cfp.default_type.pk,
            "abstract": "Ein Abstract",
            "content_locale": "de",
            "duration": 45,
            "tags": [tag.pk],
            "assigned_reviewers": [reviewer.code],
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    submission = serializer.save()

    assert submission.event == event
    assert submission.title == "German Talk"
    assert submission.content_locale == "de"
    assert submission.duration == 45
    assert list(submission.tags.all()) == [tag]
    assert list(submission.assigned_reviewers.all()) == [reviewer]


def test_submission_orga_serializer_create_defaults_content_locale_and_stores_image(
    make_image,
):
    event = EventFactory(locale="de", content_locales=["en", "de"])
    request = make_api_request(event, user=UserFactory())
    serializer = SubmissionOrgaSerializer(context={"request": request})

    submission = serializer.create(
        {
            "event": event,
            "title": "Illustrated Talk",
            "submission_type": event.cfp.default_type,
            "abstract": "An abstract",
            "image": make_image("created.png"),
        }
    )

    assert submission.content_locale == "de"
    assert submission.image.name.startswith(
        f"{event.slug}/submissions/{submission.code}/image_"
    )
    assert submission.image.name.endswith(".png")


def test_submission_orga_serializer_init_skips_content_locale_when_not_requested():
    event = EventFactory(cfp__fields={"content_locale": {"visibility": "do_not_ask"}})
    request = make_api_request(event)
    serializer = SubmissionOrgaSerializer(context={"request": request})

    assert "content_locale" not in serializer.fields


def test_submission_orga_serializer_update_sets_fields_tags_and_image(make_image):
    submission = SubmissionFactory(title="Old Title")
    tag = TagFactory(event=submission.event)
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission, context={"request": request}
    )

    updated = serializer.update(
        submission,
        {"title": "New Title", "tags": [tag], "image": make_image("new.png")},
    )

    assert updated.title == "New Title"
    assert list(updated.tags.all()) == [tag]
    assert updated.image


def test_submission_orga_serializer_update_tags_and_reviewers_from_data():
    submission = SubmissionFactory()
    event = submission.event
    old_tag = TagFactory(event=event)
    new_tags = [TagFactory(event=event), TagFactory(event=event)]
    submission.tags.add(old_tag)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    old_reviewer, new_reviewer = UserFactory(), UserFactory()
    team.members.add(old_reviewer, new_reviewer)
    submission.assigned_reviewers.add(old_reviewer)
    request = make_api_request(event)

    for data, expected_tags, expected_reviewers in (
        (
            {
                "tags": [tag.pk for tag in new_tags],
                "assigned_reviewers": [new_reviewer.code],
            },
            set(new_tags),
            {new_reviewer},
        ),
        ({"title": "Changed"}, set(new_tags), {new_reviewer}),
        ({"tags": [], "assigned_reviewers": []}, set(), set()),
    ):
        serializer = SubmissionOrgaSerializer(
            instance=submission, data=data, partial=True, context={"request": request}
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()

        assert set(submission.tags.all()) == expected_tags
        assert set(submission.assigned_reviewers.all()) == expected_reviewers


def test_submission_orga_serializer_update_rejects_cross_event_tag():
    submission = SubmissionFactory()
    foreign_tag = TagFactory(event=EventFactory())
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission,
        data={"tags": [foreign_tag.pk]},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert serializer.errors == {
        "tags": [f'Invalid pk "{foreign_tag.pk}" - object does not exist.']
    }


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
    assert serializer.errors == {"tags": ["This field may not be null."]}


def test_submission_orga_serializer_update_duration_and_slot_count_updates_slots():
    submission = SubmissionFactory(
        duration=30, slot_count=1, state=SubmissionStates.CONFIRMED
    )
    start = submission.event.datetime_from
    slot = TalkSlotFactory(
        submission=submission, start=start, end=start + dt.timedelta(minutes=30)
    )
    request = make_api_request(submission.event)
    serializer = SubmissionOrgaSerializer(
        instance=submission, context={"request": request}
    )

    serializer.update(submission, {"get_duration": 60, "slot_count": 2})
    slot.refresh_from_db()

    assert slot.end == start + dt.timedelta(minutes=60)
    assert (
        submission.event.wip_schedule.talks.filter(submission=submission).count() == 2
    )


def test_submission_orga_serializer_update_track_change_recalculates_review_scores():
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


def test_submission_orga_serializer_init_without_event():
    request = make_api_request(event=None)

    serializer = SubmissionOrgaSerializer(context={"request": request})

    assert serializer.event is None
    assert serializer.fields["reviews"].required is False


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
