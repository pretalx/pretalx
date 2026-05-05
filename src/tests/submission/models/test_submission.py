# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import statistics

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils.timezone import now, timedelta
from django_scopes import scope

from pretalx.submission.domain.submission import update_talk_slots
from pretalx.submission.models import Answer, Resource, Submission, SubmissionStates
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
    AvailabilityFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    RoomFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_generate_invite_code_length():
    code = generate_invite_code()
    assert len(code) == 32


def test_generate_invite_code_custom_length():
    code = generate_invite_code(length=16)
    assert len(code) == 16


def test_generate_invite_code_uses_valid_charset():
    code = generate_invite_code()
    assert all(c in Submission.code_charset for c in code)


def test_submission_image_path_format():
    submission = SubmissionFactory()
    path = submission_image_path(submission, "photo.jpg")
    assert path.startswith(f"{submission.event.slug}/submissions/{submission.code}/")


def test_submission_manager_excludes_drafts():
    submission = SubmissionFactory(state=SubmissionStates.DRAFT)
    assert submission not in Submission.objects.all()
    assert submission in Submission.all_objects.all()


def test_submission_all_objects_includes_drafts():
    draft = SubmissionFactory(state=SubmissionStates.DRAFT)
    submitted = SubmissionFactory(event=draft.event)
    all_subs = list(Submission.all_objects.all())
    assert draft in all_subs
    assert submitted in all_subs


def test_speaker_role_str():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)
    role = SpeakerRole.objects.get(submission=submission, speaker=speaker)
    assert str(role) == f"SpeakerRole(submission={submission.code}, speaker={speaker})"


def test_speaker_role_unique_together():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=speaker, position=0)
    with pytest.raises(IntegrityError):
        SpeakerRoleFactory(submission=submission, speaker=speaker, position=1)


def test_speaker_role_ordering():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=speaker1, position=1)
    SpeakerRoleFactory(submission=submission, speaker=speaker2, position=0)
    roles = list(SpeakerRole.objects.filter(submission=submission))
    assert roles[0].speaker == speaker2
    assert roles[1].speaker == speaker1


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


def test_submission_get_duration_default():
    submission = SubmissionFactory(duration=None)
    assert submission.get_duration() == submission.submission_type.default_duration


def test_submission_get_duration_custom():
    submission = SubmissionFactory(duration=45)
    assert submission.get_duration() == 45


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


def test_submission_reviewer_answers():
    submission = SubmissionFactory()
    event = submission.event
    q_visible = QuestionFactory(
        event=event, is_visible_to_reviewers=True, target="submission"
    )
    q_hidden = QuestionFactory(
        event=event, is_visible_to_reviewers=False, target="submission"
    )
    a_visible = AnswerFactory(question=q_visible, submission=submission)
    AnswerFactory(question=q_hidden, submission=submission)
    result = list(submission.reviewer_answers)
    assert result == [a_visible]


def test_submission_export_duration():
    submission = SubmissionFactory(duration=90)
    assert submission.export_duration == "01:30"


def test_submission_export_duration_default():
    submission = SubmissionFactory(duration=None)
    expected_minutes = submission.submission_type.default_duration
    result = submission.export_duration
    hours = expected_minutes // 60
    minutes = expected_minutes % 60
    assert result == f"{hours:02}:{minutes:02}"


def test_submission_integer_uuid():
    submission = SubmissionFactory()
    uuid_val = submission.integer_uuid
    assert isinstance(uuid_val, int)
    assert uuid_val >= 0


def test_submission_integer_uuid_deterministic():
    submission = SubmissionFactory()
    assert submission.integer_uuid == submission.integer_uuid


def test_submission_integer_uuid_unique():
    s1 = SubmissionFactory()
    s2 = SubmissionFactory(event=s1.event)
    assert s1.integer_uuid != s2.integer_uuid


def test_submission_sorted_speakers():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=speaker1, position=2)
    SpeakerRoleFactory(submission=submission, speaker=speaker2, position=1)
    result = list(submission.sorted_speakers)
    assert result == [speaker2, speaker1]


def test_submission_display_speaker_names():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event, name="Alice")
    speaker2 = SpeakerFactory(event=submission.event, name="Bob")
    SpeakerRoleFactory(submission=submission, speaker=speaker1, position=0)
    SpeakerRoleFactory(submission=submission, speaker=speaker2, position=1)
    result = submission.display_speaker_names
    assert result == "Alice, Bob"


def test_submission_display_title_with_speakers():
    submission = SubmissionFactory(title="My Talk")
    speaker = SpeakerFactory(event=submission.event, name="Alice")
    submission.speakers.add(speaker)
    result = submission.display_title_with_speakers
    assert "My Talk" in result
    assert "Alice" in result


def test_submission_display_title_with_speakers_no_speakers():
    submission = SubmissionFactory(title="Solo Talk")
    result = submission.display_title_with_speakers
    assert "Solo Talk" in result


def test_submission_median_score():
    submission = SubmissionFactory()
    ReviewFactory(submission=submission, score=1)
    ReviewFactory(submission=submission, score=3)
    ReviewFactory(submission=submission, score=5)
    assert submission.median_score == statistics.median([1, 3, 5])


def test_submission_median_score_none():
    submission = SubmissionFactory()
    assert submission.median_score is None


def test_submission_median_score_skips_none_scores():
    submission = SubmissionFactory()
    ReviewFactory(submission=submission, score=2)
    ReviewFactory(submission=submission, score=None)
    ReviewFactory(submission=submission, score=4)
    assert submission.median_score == statistics.median([2, 4])


def test_submission_mean_score():
    submission = SubmissionFactory()
    ReviewFactory(submission=submission, score=1)
    ReviewFactory(submission=submission, score=2)
    ReviewFactory(submission=submission, score=3)
    assert submission.mean_score == round(statistics.fmean([1, 2, 3]), 1)


def test_submission_mean_score_none():
    submission = SubmissionFactory()
    assert submission.mean_score is None


@pytest.mark.parametrize(
    ("content_locale", "event_locales", "fallback", "expected_locale"),
    (
        ("en", ["en", "de"], None, "en"),
        ("de", ["en", "de"], None, "de"),
        ("fr", ["en", "de"], "de", "de"),
        ("fr", ["en", "de"], "ja", "en"),
        ("fr", ["en", "de"], None, "en"),
    ),
    ids=[
        "content_locale_in_event",
        "content_locale_de_in_event",
        "fallback_used",
        "fallback_not_in_event",
        "no_fallback",
    ],
)
def test_submission_get_email_locale(
    content_locale, event_locales, fallback, expected_locale
):
    event = EventFactory(locale_array=",".join(event_locales), locale=event_locales[0])
    submission = SubmissionFactory(event=event, content_locale=content_locale)
    assert submission.get_email_locale(fallback=fallback) == expected_locale


def test_submission_clean_resets_content_locale_outside_event():
    event = EventFactory(locale_array="de", locale="de")
    submission = SubmissionFactory(event=event)
    submission.content_locale = "fr"
    submission.clean()
    assert submission.content_locale == "de"


def test_submission_get_instance_data_with_resources():
    submission = SubmissionFactory()
    ResourceFactory(
        submission=submission, link="https://example.com", description="Slides"
    )
    ResourceFactory(submission=submission, link="https://example.com/2", description="")
    data = submission.get_instance_data()
    assert data["resources"] == (
        "- [Slides](https://example.com)\n- https://example.com/2"
    )


def test_submission_get_instance_data_skips_empty_resources():
    submission = SubmissionFactory()
    ResourceFactory(submission=submission, resource=None, description=None, link=None)
    assert "resources" not in submission.get_instance_data()


def test_submission_get_instance_data_with_tags():
    submission = SubmissionFactory()
    tag = TagFactory(event=submission.event, tag="python")
    submission.tags.add(tag)
    data = submission.get_instance_data()
    assert "python" in data["tags"]


def test_submission_editable_draft_no_deadline():
    event = EventFactory(cfp__deadline=None)
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    assert submission.editable is True


def test_submission_editable_draft_past_deadline():
    event = EventFactory(cfp__deadline=now() - timedelta(hours=1))
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    assert submission.editable is False


def test_submission_editable_draft_track_requires_access_code():
    event = EventFactory()
    track = TrackFactory(event=event, requires_access_code=True)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.DRAFT, track=track
    )
    assert submission.editable is False


def test_submission_editable_draft_type_requires_access_code():
    event = EventFactory()
    st = SubmissionTypeFactory(event=event, requires_access_code=True)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.DRAFT, submission_type=st
    )
    assert submission.editable is False


def test_submission_editable_draft_with_valid_access_code():
    event = EventFactory(cfp__deadline=now() - timedelta(hours=1))
    access_code = SubmitterAccessCodeFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.DRAFT, access_code=access_code
    )
    assert submission.editable is True


def test_submission_editable_submitted_speakers_cant_edit():
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": False})
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert submission.editable is False


def test_submission_editable_submitted_with_feature_flag_and_open_deadline():
    event = EventFactory(
        cfp__deadline=now() + timedelta(hours=1),
        feature_flags={"speakers_can_edit_submissions": True},
    )
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert submission.editable is True


def test_submission_editable_accepted_with_feature_flag():
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": True})
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    assert submission.editable is True


def test_submission_editable_rejected_not_editable():
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": True})
    submission = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    assert submission.editable is False


def test_submission_user_state_review_after_deadline():
    event = EventFactory(cfp__deadline=now() - timedelta(hours=1))
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert submission.user_state == "review"


def test_submission_user_state_submitted_before_deadline():
    event = EventFactory(cfp__deadline=now() + timedelta(hours=1))
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert submission.user_state == SubmissionStates.SUBMITTED


def test_submission_user_state_accepted():
    submission = SubmissionFactory(state=SubmissionStates.ACCEPTED)
    assert submission.user_state == SubmissionStates.ACCEPTED


def test_submission_add_favourite():
    submission = SubmissionFactory()
    user = UserFactory()
    submission.add_favourite(user)
    assert SubmissionFavourite.objects.filter(user=user, submission=submission).exists()


def test_submission_add_favourite_idempotent():
    submission = SubmissionFactory()
    user = UserFactory()
    submission.add_favourite(user)
    submission.add_favourite(user)
    assert (
        SubmissionFavourite.objects.filter(user=user, submission=submission).count()
        == 1
    )


def test_submission_remove_favourite():
    submission = SubmissionFactory()
    user = UserFactory()
    submission.add_favourite(user)
    submission.remove_favourite(user)
    assert not SubmissionFavourite.objects.filter(
        user=user, submission=submission
    ).exists()


@pytest.mark.parametrize(
    ("state", "expected_count"),
    ((SubmissionStates.DRAFT, 0), (SubmissionStates.SUBMITTED, 1)),
    ids=["draft_skipped", "submitted_logged"],
)
def test_submission_log_action(state, expected_count):
    """log_action is a no-op for draft submissions but works for non-drafts."""
    submission = SubmissionFactory(state=state)
    submission.log_action("pretalx.submission.test")
    assert submission.logged_actions().count() == expected_count


def test_submission_slot_no_current_schedule():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    with scope(event=submission.event):
        assert submission.slot is None


def test_submission_current_slots_no_current_schedule():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    with scope(event=submission.event):
        assert submission.current_slots is None


def test_submission_public_slots_no_visible_agenda():
    event = EventFactory(is_public=False)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        assert submission.public_slots == []


def test_submission_does_accept_feedback_no_slot():
    submission = SubmissionFactory()
    with scope(event=submission.event):
        assert submission.does_accept_feedback is False


def test_submission_delete_removes_related():
    submission = SubmissionFactory()
    event = submission.event
    AnswerFactory(question=QuestionFactory(event=event), submission=submission)
    ResourceFactory(submission=submission)
    sub_pk = submission.pk
    with scope(event=event):
        submission.delete()
    assert not Submission.all_objects.filter(pk=sub_pk).exists()
    assert not Answer.objects.filter(submission_id=sub_pk).exists()
    assert not Resource.objects.filter(submission_id=sub_pk).exists()


def test_submission_delete_removes_review_answers():
    submission = SubmissionFactory()
    event = submission.event
    review = ReviewFactory(submission=submission)
    reviewer_question = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    review_answer = AnswerFactory(
        question=reviewer_question, submission=None, review=review
    )
    review_answer_pk = review_answer.pk
    sub_pk = submission.pk
    with scope(event=event):
        submission.delete()
    assert not Submission.all_objects.filter(pk=sub_pk).exists()
    assert not Answer.objects.filter(pk=review_answer_pk).exists()


def test_submission_delete_cleans_up_resource_files(django_capture_on_commit_callbacks):
    submission = SubmissionFactory()
    f = SimpleUploadedFile("testresource.txt", b"test content")
    resource = ResourceFactory(
        submission=submission, resource=f, description="Test resource"
    )
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)
    with (
        scope(event=submission.event),
        django_capture_on_commit_callbacks(execute=True),
    ):
        submission.delete()
    assert not resource.resource.storage.exists(file_path)


def test_submission_invitation_str():
    submission = SubmissionFactory()
    invitation = SubmissionInvitationFactory(
        submission=submission, email="test@example.com"
    )
    result = str(invitation)
    assert submission.title in result
    assert "test@example.com" in result


def test_submission_invitation_event():
    submission = SubmissionFactory()
    invitation = SubmissionInvitationFactory(
        submission=submission, email="test@example.com"
    )
    assert invitation.event == submission.event


def test_submission_invitation_unique_together():
    submission = SubmissionFactory()
    SubmissionInvitationFactory(submission=submission, email="test@example.com")
    with pytest.raises(IntegrityError):
        SubmissionInvitationFactory(submission=submission, email="test@example.com")


def test_submission_score_categories_with_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    cat_all = ReviewScoreCategoryFactory(event=event, name="General", active=True)
    cat_track = ReviewScoreCategoryFactory(
        event=event, name="Track-specific", active=True
    )
    cat_track.limit_tracks.add(track)
    cat_inactive = ReviewScoreCategoryFactory(
        event=event, name="Inactive", active=False
    )

    submission = SubmissionFactory(event=event, track=track)
    categories = list(submission.score_categories)
    assert cat_all in categories
    assert cat_track in categories
    assert cat_inactive not in categories


def test_submission_score_categories_no_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    cat_all = ReviewScoreCategoryFactory(event=event, name="General", active=True)
    cat_track = ReviewScoreCategoryFactory(
        event=event, name="Track-specific", active=True
    )
    cat_track.limit_tracks.add(track)

    submission = SubmissionFactory(event=event, track=None)
    categories = list(submission.score_categories)
    assert cat_all in categories
    assert cat_track not in categories


def test_submission_editable_unsaved():
    submission = Submission()
    assert submission.editable is True


def test_submission_public_answers():
    submission = SubmissionFactory()
    event = submission.event
    q_public = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    q_private = QuestionFactory(
        event=event, is_public=False, target=QuestionTarget.SUBMISSION
    )
    a_public = AnswerFactory(question=q_public, submission=submission)
    AnswerFactory(question=q_private, submission=submission)
    result = list(submission.public_answers)
    assert result == [a_public]


def test_submission_public_answers_with_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    q_track = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    q_other_track = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    other_track = TrackFactory(event=event)
    q_track.tracks.add(track)
    q_other_track.tracks.add(other_track)
    a_track = AnswerFactory(question=q_track, submission=submission)
    AnswerFactory(question=q_other_track, submission=submission)
    result = list(submission.public_answers)
    assert a_track in result
    assert all(a.question != q_other_track for a in result)


def test_submission_get_content_locale_display():
    submission = SubmissionFactory(content_locale="en")
    result = submission.get_content_locale_display()
    assert result == "English"


def test_submission_get_content_locale_display_locale_not_in_event():
    """When a submission's content_locale is not in the event's content_locales,
    get_content_locale_display should still return a human-readable name."""
    event = EventFactory()  # default content_locales is ['en']
    submission = SubmissionFactory(event=event, content_locale="de-formal")
    result = submission.get_content_locale_display()
    assert result == "Deutsch"


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
        event.release_schedule(name="v1")
    with scope(event=event):
        assert submission.does_accept_feedback is True


def test_submission_public_slots_with_visible_agenda():
    """public_slots delegates to current_slots when the agenda is visible,
    rather than returning the early-exit empty list."""
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    with scope(event=submission.event):
        update_talk_slots(submission)
        submission.event.release_schedule(name="v1")
        result = submission.public_slots
    assert result is not None


def test_submission_current_slots_with_schedule():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        update_talk_slots(submission)
        event.release_schedule(name="v1")
        result = submission.current_slots
    assert result is not None


def test_submission_active_resources():
    submission = SubmissionFactory()
    r_link = ResourceFactory(submission=submission, link="https://example.com")
    ResourceFactory(submission=submission, link="")
    result = list(submission.active_resources)
    assert result == [r_link]


def test_submission_private_resources():
    submission = SubmissionFactory()
    ResourceFactory(submission=submission, link="https://example.com", is_public=False)
    ResourceFactory(submission=submission, link="https://public.com", is_public=True)
    result = list(submission.private_resources)
    assert len(result) == 1
    assert result[0].is_public is False


def test_submission_public_resources():
    submission = SubmissionFactory()
    ResourceFactory(submission=submission, link="https://example.com", is_public=False)
    r_public = ResourceFactory(
        submission=submission, link="https://public.com", is_public=True
    )
    result = list(submission.public_resources)
    assert result == [r_public]


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


def test_submission_get_instance_data_unsaved():
    submission = Submission(title="Unsaved", code="ABCDEF")
    data = submission.get_instance_data()
    assert "resources" not in data
    assert "tags" not in data


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
        position=0,
        speakers_can_change_submissions=True,
        is_active=True,
    )
    event = refresh(event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        assert submission.editable is True
