# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.db import IntegrityError
from django.utils.timezone import now, timedelta
from django_scopes import scope

from pretalx.event.models import Event
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.domain.queries.submission import (
    annotate_confirmed_signup_count,
    annotate_requires_signup,
    annotate_submission_signup_status,
)
from pretalx.submission.domain.submission import update_talk_slots
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import Submission, SubmissionStates
from pretalx.submission.models.question import QuestionTarget
from pretalx.submission.models.review import ReviewPhase
from pretalx.submission.models.submission import (
    SpeakerRole,
    SubmissionFavourite,
    generate_invite_code,
    submission_image_path,
)
from tests.factories import (
    AnswerFactory,
    AttendeeSignupFactory,
    AvailabilityFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_generate_invite_code():
    code = generate_invite_code()

    assert len(code) == 32
    assert len(generate_invite_code(length=16)) == 16
    assert all(c in Submission.code_charset for c in code)


def test_submission_image_path_format():
    submission = SubmissionFactory()
    path = submission_image_path(submission, "photo.jpg")
    assert path.startswith(f"{submission.event.slug}/submissions/{submission.code}/")


def test_submission_manager_excludes_drafts():
    submission = SubmissionFactory(state=SubmissionStates.DRAFT)
    assert submission not in Submission.objects.all()
    assert submission in Submission.all_objects.all()


def test_submission_speakers_follow_role_positions():
    submission = SubmissionFactory(title="My Talk")
    solo = SubmissionFactory(event=submission.event, title="Solo Talk")
    alice = SpeakerFactory(event=submission.event, name="Alice")
    bob = SpeakerFactory(event=submission.event, name="Bob")
    SpeakerRoleFactory(submission=submission, speaker=alice, position=1)
    SpeakerRoleFactory(submission=submission, speaker=bob, position=0)
    roles = list(
        SpeakerRole.objects.select_related(
            "submission", "speaker__event", "speaker__user"
        ).filter(submission=submission)
    )

    assert [role.speaker for role in roles] == [bob, alice]
    assert str(roles[0]) == f"SpeakerRole(submission={submission.code}, speaker={bob})"
    assert list(submission.sorted_speakers) == [bob, alice]
    assert submission.display_speaker_names == "Bob, Alice"
    assert submission.display_title_with_speakers == "“My Talk” by Bob, Alice"
    assert solo.display_title_with_speakers == "“Solo Talk”"
    with pytest.raises(IntegrityError):
        SpeakerRoleFactory(submission=submission, speaker=alice, position=2)


@pytest.mark.parametrize(
    ("has_pk", "expected_format"),
    ((True, "with_pk"), (False, "no_pk")),
    ids=["with_pk", "no_pk"],
)
def test_submission_str(has_pk, expected_format):
    if has_pk:
        submission = SubmissionFactory()
        expected = f"Submission(event={submission.event.slug}, code={submission.code}, title={submission.title}, state={submission.state})"
    else:
        submission = Submission(code="ABCDEF", title="Test Talk", state="submitted")
        expected = "Submission(code=ABCDEF, title=Test Talk, state=submitted)"
    assert str(submission) == expected


def test_submission_image_url_no_image():
    submission = Submission()
    assert submission.image_url == ""


def test_submission_log_parent():
    submission = SubmissionFactory()
    assert submission.log_parent == submission.event


def test_submission_get_duration_falls_back_to_type_default():
    submission_type = SubmissionTypeFactory(default_duration=100)
    default = SubmissionFactory(
        event=submission_type.event, submission_type=submission_type, duration=None
    )
    custom = SubmissionFactory(
        event=submission_type.event, submission_type=submission_type, duration=90
    )

    assert default.get_duration() == 100
    assert default.export_duration == "01:40"
    assert custom.get_duration() == 90
    assert custom.export_duration == "01:30"


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        (None, False),
        ({}, False),
        ({"_anonymised": True}, True),
        ({"_anonymised": False}, False),
    ),
    ids=["none", "empty_dict", "anonymised_true", "anonymised_false"],
)
def test_submission_is_anonymised(data, expected):
    s = Submission()
    s.anonymised = data
    assert s.is_anonymised is expected


@pytest.mark.parametrize(
    ("anonymised", "expected"),
    (
        (None, "Original"),
        ({}, "Original"),
        ({"_anonymised": True}, "Original"),
        ({"_anonymised": True, "title": "Redacted"}, "Redacted"),
        ({"_anonymised": True, "title": ""}, ""),
        ({"_anonymised": False, "title": "Redacted"}, "Original"),
    ),
    ids=["none", "empty_dict", "key_absent", "redacted", "blanked", "not_anonymised"],
)
def test_submission_get_anonymised(anonymised, expected):
    s = Submission(title="Original")
    s.anonymised = anonymised
    assert s.get_anonymised("title") == expected


def test_submission_reviewer_answers():
    submission = SubmissionFactory()
    event = submission.event
    q_visible = QuestionFactory(
        event=event, is_visible_to_reviewers=True, target=QuestionTarget.SUBMISSION
    )
    q_hidden = QuestionFactory(
        event=event, is_visible_to_reviewers=False, target=QuestionTarget.SUBMISSION
    )
    a_visible = AnswerFactory(question=q_visible, submission=submission)
    AnswerFactory(question=q_hidden, submission=submission)
    assert list(submission.reviewer_answers) == [a_visible]


def test_submission_integer_uuid_unique():
    s1 = SubmissionFactory()
    s2 = SubmissionFactory(event=s1.event)
    assert s1.integer_uuid != s2.integer_uuid


def test_submission_scores_skip_missing_values():
    unreviewed = SubmissionFactory()
    reviewed = SubmissionFactory(event=unreviewed.event)
    for score in (1, None, 2, 6):
        ReviewFactory(submission=reviewed, score=score)

    assert unreviewed.median_score is None
    assert unreviewed.mean_score is None
    assert reviewed.median_score == 2
    assert reviewed.mean_score == 3.0


def test_submission_get_email_locale():
    event = EventFactory(locales=["en", "de"], locale="en")
    english = SubmissionFactory(event=event, content_locale="en")
    german = SubmissionFactory(event=event, content_locale="de")
    french = SubmissionFactory(event=event, content_locale="fr")

    assert english.get_email_locale() == "en"
    assert german.get_email_locale() == "de"
    assert french.get_email_locale(fallback="de") == "de"
    assert french.get_email_locale(fallback="ja") == "en"
    assert french.get_email_locale() == "en"


def test_submission_clean_resets_content_locale_outside_event():
    event = EventFactory(locales=["de"], locale="de")
    submission = SubmissionFactory(event=event)
    submission.content_locale = "fr"
    submission.clean()
    assert submission.content_locale == "de"


def test_submission_get_instance_data_lists_resources_and_tags():
    submission = SubmissionFactory()
    ResourceFactory(
        submission=submission, link="https://example.com", description="Slides"
    )
    ResourceFactory(submission=submission, link="https://example.com/2", description="")
    ResourceFactory(submission=submission, resource=None, description="", link=None)
    submission.tags.add(TagFactory(event=submission.event, tag="python"))
    bare = SubmissionFactory(event=submission.event)
    ResourceFactory(submission=bare, resource=None, description="", link=None)
    unsaved = Submission(title="Unsaved", code="ABCDEF")

    data = submission.get_instance_data()
    bare_data = bare.get_instance_data()
    unsaved_data = unsaved.get_instance_data()

    assert (
        data["resources"] == "- [Slides](https://example.com)\n- https://example.com/2"
    )
    assert data["tags"] == "- python"
    assert "resources" not in bare_data
    assert bare_data["tags"] == ""
    assert "resources" not in unsaved_data
    assert "tags" not in unsaved_data


def test_submission_editable_draft_needs_open_cfp_or_access_code():
    closed = EventFactory(cfp__deadline=now() - timedelta(hours=1))
    access_code = SubmitterAccessCodeFactory(event=closed)
    restricted_track = TrackFactory(event=closed, requires_access_code=True)
    restricted_type = SubmissionTypeFactory(event=closed, requires_access_code=True)
    open_event = EventFactory(cfp__deadline=None)

    def draft(event, **kwargs):
        return SubmissionFactory(event=event, state=SubmissionStates.DRAFT, **kwargs)

    assert draft(closed).editable is False
    assert draft(closed, access_code=access_code).editable is True
    assert draft(open_event).editable is True
    assert draft(open_event, track=restricted_track).editable is False
    assert draft(open_event, submission_type=restricted_type).editable is False


def test_submission_editable_by_state_and_cfp():
    open_event = EventFactory(cfp__deadline=now() + timedelta(hours=1))
    closed = EventFactory(cfp__deadline=now() - timedelta(hours=1))
    locked = EventFactory(feature_flags={"speakers_can_edit_submissions": False})

    def submission(event, state):
        return SubmissionFactory(event=event, state=state)

    assert Submission().editable is True
    assert submission(open_event, SubmissionStates.SUBMITTED).editable is True
    assert submission(open_event, SubmissionStates.ACCEPTED).editable is True
    assert submission(open_event, SubmissionStates.REJECTED).editable is False
    assert submission(closed, SubmissionStates.SUBMITTED).editable is False
    assert submission(closed, SubmissionStates.ACCEPTED).editable is True
    assert submission(locked, SubmissionStates.SUBMITTED).editable is False
    assert submission(locked, SubmissionStates.ACCEPTED).editable is False


def test_submission_editable_submitted_past_deadline_with_review_phase():
    event = EventFactory(
        cfp__deadline=now() - timedelta(hours=1),
        feature_flags={"speakers_can_edit_submissions": True},
    )
    with scope(event=event):
        ReviewPhase.objects.filter(event=event).update(is_active=False)
    ReviewPhaseFactory(
        event=event,
        name="Open Review",
        speakers_can_change_submissions=True,
        is_active=True,
    )
    event = Event.objects.select_related("cfp__default_type").get(pk=event.pk)
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        assert submission.editable is True


def test_submission_user_state_shows_review_after_deadline():
    closed = EventFactory(cfp__deadline=now() - timedelta(hours=1))
    open_event = EventFactory(cfp__deadline=now() + timedelta(hours=1))

    assert (
        SubmissionFactory(event=closed, state=SubmissionStates.SUBMITTED).user_state
        == "review"
    )
    assert (
        SubmissionFactory(event=closed, state=SubmissionStates.ACCEPTED).user_state
        == SubmissionStates.ACCEPTED
    )
    assert (
        SubmissionFactory(event=open_event, state=SubmissionStates.SUBMITTED).user_state
        == SubmissionStates.SUBMITTED
    )


def test_submission_favourite_add_is_idempotent_and_remove_clears():
    submission = SubmissionFactory()
    user = UserFactory()
    favourites = SubmissionFavourite.objects.filter(user=user, submission=submission)

    submission.add_favourite(user)
    submission.add_favourite(user)
    assert favourites.count() == 1

    submission.remove_favourite(user)
    assert not favourites.exists()


@pytest.mark.parametrize(
    ("state", "expected_count"),
    ((SubmissionStates.DRAFT, 0), (SubmissionStates.SUBMITTED, 1)),
    ids=["draft_skipped", "submitted_logged"],
)
def test_submission_log_action(state, expected_count):
    submission = SubmissionFactory(state=state)
    submission.log_action("pretalx.submission.test")
    assert submission.logged_actions().count() == expected_count


def test_submission_slots_without_current_schedule():
    event = EventFactory(is_public=False)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    with scope(event=event):
        assert submission.slot is None
        assert submission.current_slots is None
        assert submission.public_slots == []
        assert submission.does_accept_feedback is False
        assert submission.is_over is False


def test_submission_invitation():
    submission = SubmissionFactory(title="My Talk")
    invitation = SubmissionInvitationFactory(
        submission=submission, email="test@example.com"
    )

    assert str(invitation) == "Invite to My Talk for test@example.com"
    assert invitation.event == submission.event
    with pytest.raises(IntegrityError):
        SubmissionInvitationFactory(submission=submission, email="test@example.com")


def test_submission_score_categories_follow_track():
    event = EventFactory()
    event.score_categories.all().delete()
    track = TrackFactory(event=event)
    cat_all = ReviewScoreCategoryFactory(event=event, name="General", active=True)
    cat_track = ReviewScoreCategoryFactory(
        event=event, name="Track-specific", active=True
    )
    cat_track.limit_tracks.add(track)
    ReviewScoreCategoryFactory(event=event, name="Inactive", active=False)
    on_track = SubmissionFactory(event=event, track=track)
    trackless = SubmissionFactory(event=event, track=None)

    assert list(on_track.score_categories) == [cat_all, cat_track]
    assert list(trackless.score_categories) == [cat_all]


def test_submission_get_content_locale_display():
    event = EventFactory()
    english = SubmissionFactory(event=event, content_locale="en")
    german = SubmissionFactory(event=event, content_locale="de-formal")

    assert english.get_content_locale_display() == "English"
    assert german.get_content_locale_display() == "Deutsch"


@pytest.mark.parametrize(
    ("content_locale", "expected"),
    (("en", "en"), ("de-formal", "de"), ("zh-hant", "zh-Hant"), ("en-gb", "en-gb")),
)
def test_submission_content_language_tag(content_locale, expected):
    submission = Submission(content_locale=content_locale)

    assert submission.content_language_tag == expected


def test_submission_does_accept_feedback_with_past_slot():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    with scope(event=event):
        update_talk_slots(submission)
        slot = event.wip_schedule.talks.get(submission=submission)
        slot.start = now() - timedelta(hours=2)
        slot.end = now() - timedelta(hours=1)
        slot.room = room
        slot.save()
        freeze_schedule(event.wip_schedule, name="v1")
    with scope(event=event):
        assert submission.does_accept_feedback is True


@pytest.mark.parametrize(
    ("slot_hours", "expected"),
    (
        (((-2, -1),), True),
        (((-1, 1),), False),
        (((1, 2),), False),
        (((-4, -3), (-2, -1)), True),
        (((-4, -3), (-2, 3)), False),
        (((None, None),), False),
    ),
)
def test_submission_is_over(slot_hours, expected):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        for start, end in slot_hours:
            TalkSlotFactory(
                submission=submission,
                is_visible=True,
                start=now() + timedelta(hours=start) if start is not None else None,
                end=now() + timedelta(hours=end) if end is not None else None,
            )
        freeze_schedule(event.wip_schedule, name="v1")

    with scope(event=event):
        assert submission.is_over is expected


def test_submission_current_and_public_slots_with_released_schedule():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    with scope(event=event):
        update_talk_slots(submission)
        slot = event.wip_schedule.talks.get(submission=submission)
        slot.room = RoomFactory(event=event)
        slot.start = event.datetime_from
        slot.end = event.datetime_from + dt.timedelta(minutes=30)
        slot.save()
        freeze_schedule(event.wip_schedule, name="v1")
        current = list(submission.current_slots)
        public = list(submission.public_slots)

    assert [s.pk for s in current] == [submission.slot.pk]
    assert current[0].submission == submission
    assert public == current


def test_submission_resources_split_by_visibility():
    submission = SubmissionFactory()
    private = ResourceFactory(
        submission=submission, link="https://example.com", is_public=False
    )
    public = ResourceFactory(
        submission=submission, link="https://public.com", is_public=True
    )
    ResourceFactory(submission=submission, link="")
    ResourceFactory(submission=submission, link="", resource="None")

    assert submission.active_resources == [private, public]
    assert submission.private_resources == [private]
    assert submission.public_resources == [public]


def test_submission_availabilities():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    AvailabilityFactory(
        event=event,
        person=speaker,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=4),
    )
    with scope(event=event):
        result = submission.availabilities
    assert len(result) == 1
    assert result[0].start == event.datetime_from
    assert result[0].end == event.datetime_from + dt.timedelta(hours=4)


@pytest.mark.parametrize(
    ("state", "feature_enabled", "has_review_code", "expected"),
    (
        (SubmissionStates.SUBMITTED, True, True, True),
        (SubmissionStates.DRAFT, True, True, True),
        (SubmissionStates.ACCEPTED, True, True, True),
        (SubmissionStates.CONFIRMED, True, True, True),
        (SubmissionStates.SUBMITTED, False, True, False),
        (SubmissionStates.SUBMITTED, True, False, False),
        (SubmissionStates.REJECTED, True, True, False),
        (SubmissionStates.REJECTED, False, True, False),
        (SubmissionStates.WITHDRAWN, True, True, False),
        (SubmissionStates.CANCELED, True, True, False),
    ),
)
def test_submission_public_review_link_active(
    state, feature_enabled, has_review_code, expected, django_assert_num_queries
):
    event = EventFactory(feature_flags={"submission_public_review": feature_enabled})
    submission = SubmissionFactory(
        event=event, state=state, review_code="abcd1234" if has_review_code else None
    )
    with scope(event=event):
        loaded = Submission.all_objects.select_related("event").get(pk=submission.pk)

    with django_assert_num_queries(0):
        assert loaded.public_review_link_active is expected


@pytest.mark.parametrize(
    ("submission_override", "track_required", "type_required", "expected"),
    (
        (True, False, False, True),
        (False, True, True, False),
        (None, True, False, True),
        (None, False, True, True),
        (None, False, False, False),
    ),
    ids=(
        "override_true_wins",
        "override_false_wins",
        "track_only",
        "type_only",
        "no_inheritance",
    ),
)
def test_submission_requires_signup_computes_from_overrides_and_inheritance(
    submission_override, track_required, type_required, expected
):
    event = EventFactory()
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    track = TrackFactory(event=event, attendee_signup_required=track_required)
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        track=track,
        attendee_signup_required=submission_override,
    )

    assert submission.requires_signup is expected


def test_submission_requires_signup_without_track_or_type():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    trackless = SubmissionFactory(event=event, submission_type=sub_type, track=None)

    assert trackless.requires_signup is True
    assert Submission(event=event).requires_signup is False


def test_submission_requires_signup_uses_annotation_when_present(
    django_assert_num_queries,
):
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    # Submission-level override is null so the fallback would otherwise have
    # to consult ``submission_type`` (and ``track``); with the annotation
    # active the property must short-circuit on the SQL value.
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_required=None
    )

    with scope(event=event):
        annotated = annotate_requires_signup(event.submissions.all()).get(
            pk=submission.pk
        )

    with django_assert_num_queries(0):
        result = annotated.requires_signup

    assert result is True


def test_submission_confirmed_signup_count(django_assert_num_queries):
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)
        AttendeeSignupFactory(submission=submission)
        AttendeeSignupFactory(
            submission=submission, state=AttendeeSignupStates.CANCELED
        )
        assert submission.confirmed_signup_count == 2
        annotated = annotate_confirmed_signup_count(event.submissions.all()).get(
            pk=submission.pk
        )

    with django_assert_num_queries(0):
        assert annotated.confirmed_signup_count == 2


def test_submission_effective_signup_capacity_prefers_override(
    django_assert_num_queries,
):
    event = EventFactory()
    overridden = SubmissionFactory(event=event, attendee_signup_capacity=42)
    plain = SubmissionFactory(event=event)
    annotated = SubmissionFactory(event=event, attendee_signup_capacity=42)
    annotated._annotated_signup_capacity = None

    assert overridden.effective_signup_capacity == 42
    assert plain.effective_signup_capacity is None
    with django_assert_num_queries(0):
        assert annotated.effective_signup_capacity is None


def test_submission_effective_signup_capacity_falls_back_to_room(
    django_assert_num_queries,
):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    schedule = ScheduleFactory(event=event, version="v1")
    room = RoomFactory(event=event, capacity=88)
    with scope(event=event):
        TalkSlotFactory(submission=submission, schedule=schedule, room=room)
        annotated = annotate_submission_signup_status(
            event.submissions.all(), event.current_schedule
        ).get(pk=submission.pk)
    submission = Submission.objects.select_related("event").get(pk=submission.pk)

    assert submission.effective_signup_capacity == 88
    with django_assert_num_queries(0):
        assert annotated.effective_signup_capacity == 88


@pytest.mark.parametrize(
    ("capacity", "confirmed", "places_left", "percent"),
    ((None, 1, None, None), (5, 2, 3, 40), (2, 3, 0, 100), (10, 3, 7, 30)),
    ids=("unlimited", "places_remaining", "never_negative", "under_capacity"),
)
def test_submission_signup_places_left_and_percent(
    capacity, confirmed, places_left, percent
):
    event = EventFactory()
    submission = SubmissionFactory(event=event, attendee_signup_capacity=capacity)
    with scope(event=event):
        for _ in range(confirmed):
            AttendeeSignupFactory(submission=submission)
    submission = Submission.objects.select_related("event").get(pk=submission.pk)

    assert submission.signup_places_left == places_left
    assert submission.signup_capacity_percent == percent


@pytest.mark.parametrize(
    ("feature", "type_required", "capacity", "confirmed", "expected"),
    (
        (False, True, 10, 0, None),
        (True, False, 10, 0, None),
        (True, True, 10, 0, "open"),
        (True, True, 1, 1, "full"),
        (True, True, None, 0, "open"),
    ),
    ids=(
        "feature_disabled",
        "signup_not_required",
        "open_when_under_capacity",
        "full_when_at_capacity",
        "open_without_capacity_info",
    ),
)
def test_submission_signup_status(
    feature, type_required, capacity, confirmed, expected
):
    event = EventFactory(feature_flags={"attendee_signup": feature})
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=capacity
    )
    with scope(event=event):
        for _ in range(confirmed):
            AttendeeSignupFactory(submission=submission)
    submission = Submission.objects.select_related("event", "submission_type").get(
        pk=submission.pk
    )
    assert submission.signup_status == expected


def test_submission_signup_status_uses_annotation_when_present(
    django_assert_num_queries,
):
    # Non-signup sessions are the common case on annotated querysets, and
    # falling through to live compute would re-issue per-row signup queries.
    # The property uses ``hasattr`` so the short-circuit fires even when the
    # annotation value is ``None``.
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    full = SubmissionFactory(event=event, submission_type=sub_type)
    full._annotated_signup_status = "full"
    empty = SubmissionFactory(event=event, submission_type=sub_type)
    empty._annotated_signup_status = None

    with django_assert_num_queries(0):
        assert full.signup_status == "full"
        assert empty.signup_status is None
