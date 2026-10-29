# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope

from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.question import (
    active_questions,
    answers_for_user,
    count_missing_answers,
    missing_questions_for_speaker,
    public_answers_for_speaker,
    public_answers_for_submission,
    question_answer_summary,
    question_scope_speakers,
    question_scope_submissions,
    questions_for_user,
)
from pretalx.submission.enums import QuestionVariant, SubmissionStates
from pretalx.submission.models.question import QuestionTarget
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _team_user(event, **team_kwargs):
    team = TeamFactory(organiser=event.organiser, all_events=True, **team_kwargs)
    user = UserFactory()
    team.members.add(user)
    return user


def test_active_questions_filters_by_target_scope_and_reviewer_visibility():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    sub_type = SubmissionTypeFactory(event=event)
    other_type = SubmissionTypeFactory(event=event)
    inactive = QuestionFactory(event=event, active=False)
    general = QuestionFactory(event=event)
    speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    reviewer_q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    hidden = QuestionFactory(event=event, is_visible_to_reviewers=False)
    track_q = QuestionFactory(event=event)
    track_q.tracks.add(track)
    other_track_q = QuestionFactory(event=event)
    other_track_q.tracks.add(other_track)
    typed_q = QuestionFactory(event=event)
    typed_q.submission_types.add(sub_type)
    other_typed_q = QuestionFactory(event=event)
    other_typed_q.submission_types.add(other_type)
    submission_questions = {
        general,
        hidden,
        track_q,
        other_track_q,
        typed_q,
        other_typed_q,
    }

    with scope(event=event):
        assert set(active_questions(event)) == submission_questions
        assert inactive not in set(active_questions(event))
        assert set(active_questions(event, target=QuestionTarget.SPEAKER)) == {
            speaker_q
        }
        assert set(active_questions(event, target=None)) == submission_questions | {
            speaker_q
        }
        assert reviewer_q not in set(active_questions(event, target=None))
        assert set(active_questions(event, track=track)) == submission_questions - {
            other_track_q
        }
        assert set(
            active_questions(event, submission_type=sub_type)
        ) == submission_questions - {other_typed_q}
        assert set(active_questions(event, skip_limited=True)) == {general, hidden}
        assert set(
            active_questions(event, for_reviewers=True)
        ) == submission_questions - {hidden}


def test_questions_and_answers_for_user_by_role():
    event = EventFactory()
    editor = _team_user(event, can_change_submissions=True)
    settings_only = _team_user(
        event, can_change_event_settings=True, can_change_submissions=False
    )
    reviewer = _team_user(event, is_reviewer=True, can_change_submissions=False)
    reviewer_with_settings = _team_user(
        event, is_reviewer=True, can_change_submissions=False
    )
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=False,
    ).members.add(reviewer_with_settings)
    other_team = TeamFactory(organiser=event.organiser, all_events=True)
    event.review_phases.filter(is_active=True).update(can_see_speaker_names=True)

    inactive = QuestionFactory(event=event, active=False)
    visible = QuestionFactory(event=event, is_visible_to_reviewers=True)
    hidden = QuestionFactory(event=event, is_visible_to_reviewers=False)
    reviewer_q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    public = QuestionFactory(event=event, is_public=True)
    restricted = QuestionFactory(event=event)
    restricted.limit_teams.add(other_team)
    visible_answer = AnswerFactory(question=visible)
    AnswerFactory(question=restricted)
    unrestricted = {inactive, visible, hidden, reviewer_q, public}

    with scope(event=event):
        assert set(questions_for_user(event, editor)) == unrestricted
        assert set(questions_for_user(event, settings_only)) == unrestricted
        assert set(questions_for_user(event, reviewer)) == {visible, reviewer_q, public}
        assert set(questions_for_user(event, reviewer_with_settings)) == {
            visible,
            reviewer_q,
            public,
        }
        assert list(questions_for_user(event, AnonymousUser())) == [public]
        assert list(answers_for_user(event, editor)) == [visible_answer]

    private_event = EventFactory(is_public=False)
    AnswerFactory(question=QuestionFactory(event=private_event, is_public=True))
    with scope(event=private_event):
        assert list(questions_for_user(private_event, AnonymousUser())) == []
        assert list(answers_for_user(private_event, AnonymousUser())) == []


def test_count_missing_answers_per_target_and_filter():
    event = EventFactory()
    sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    reviewer_q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    sub1.speakers.add(speaker1)
    sub2.speakers.add(speaker2)

    with scope(event=event):
        assert count_missing_answers(sub_q) == 2
        assert count_missing_answers(speaker_q) == 2
        assert count_missing_answers(reviewer_q) == 0

        AnswerFactory(question=sub_q, submission=sub1, speaker=None)
        AnswerFactory(question=speaker_q, speaker=speaker1, submission=None)

        assert count_missing_answers(sub_q) == 1
        assert count_missing_answers(speaker_q) == 1
        only_sub1 = event.submissions.filter(pk=sub1.pk)
        only_sub2 = event.submissions.filter(pk=sub2.pk)
        assert count_missing_answers(sub_q, filter_talks=only_sub1) == 0
        assert count_missing_answers(sub_q, filter_talks=only_sub2) == 1
        only_speaker1 = SpeakerProfile.objects.filter(pk=speaker1.pk)
        only_speaker2 = SpeakerProfile.objects.filter(pk=speaker2.pk)
        assert count_missing_answers(speaker_q, filter_speakers=only_speaker1) == 0
        assert count_missing_answers(speaker_q, filter_speakers=only_speaker2) == 1


def test_public_answers_for_submission_filters_public_active_and_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    q_public = QuestionFactory(event=event, is_public=True, position=2)
    q_private = QuestionFactory(event=event, is_public=False)
    q_inactive = QuestionFactory(event=event, is_public=True, active=False)
    q_track = QuestionFactory(event=event, is_public=True, position=1)
    q_track.tracks.add(track)
    q_other_track = QuestionFactory(event=event, is_public=True)
    q_other_track.tracks.add(other_track)
    a_public = AnswerFactory(question=q_public, submission=submission)
    a_track = AnswerFactory(question=q_track, submission=submission)
    for question in (q_private, q_inactive, q_other_track):
        AnswerFactory(question=question, submission=submission)

    trackless = SubmissionFactory(event=event, track=None)
    trackless_answer = AnswerFactory(question=q_other_track, submission=trackless)

    with scope(event=event):
        assert list(public_answers_for_submission(submission)) == [a_track, a_public]
        assert list(public_answers_for_submission(trackless)) == [trackless_answer]


def test_public_answers_for_speaker_filters_and_orders_by_position():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    later = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SPEAKER, position=2
    )
    earlier = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SPEAKER, position=1
    )
    private_q = QuestionFactory(
        event=event, is_public=False, target=QuestionTarget.SPEAKER
    )
    inactive_q = QuestionFactory(
        event=event, is_public=True, active=False, target=QuestionTarget.SPEAKER
    )
    submission_q = QuestionFactory(event=event, is_public=True)
    later_answer = AnswerFactory(question=later, speaker=speaker, submission=None)
    earlier_answer = AnswerFactory(question=earlier, speaker=speaker, submission=None)
    AnswerFactory(question=private_q, speaker=speaker, submission=None)
    AnswerFactory(question=inactive_q, speaker=speaker, submission=None)
    AnswerFactory(question=submission_q, speaker=speaker, submission=submission)

    with scope(event=event):
        assert list(public_answers_for_speaker(speaker)) == [
            earlier_answer,
            later_answer,
        ]


def test_missing_questions_for_speaker_lists_each_unanswered_question_once():
    event = EventFactory()
    q_sub = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    q_sub_other = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    q_speaker = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    q_speaker_other = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    q_reviewer = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    speaker = SpeakerFactory(event=event)
    for _ in range(2):
        SubmissionFactory(event=event).speakers.add(speaker)
    AnswerFactory(question=q_speaker, speaker=speaker, answer="answered")

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker,
            submissions=event.submissions.all(),
            questions=[q_reviewer, q_sub, q_speaker, q_sub_other, q_speaker_other],
        )

    assert missing == [q_sub, q_sub_other, q_speaker_other]


@pytest.mark.parametrize("target", (QuestionTarget.SUBMISSION, QuestionTarget.SPEAKER))
@pytest.mark.parametrize(
    ("question_track", "question_type", "submission_track", "expected"),
    (
        ("same", None, "same", True),
        ("other", None, "same", False),
        ("other", None, None, True),
        (None, "same", "same", True),
        (None, "other", "same", False),
        ("same", "other", "same", False),
        ("other", "same", "same", False),
    ),
    ids=(
        "track_match",
        "track_mismatch",
        "trackless_submission",
        "type_match",
        "type_mismatch",
        "track_match_type_mismatch",
        "type_match_track_mismatch",
    ),
)
def test_missing_questions_for_speaker_respects_restrictions(
    target, question_track, question_type, submission_track, expected
):
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    other_type = SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(
        event=event, track=track if submission_track else None
    )
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    question = QuestionFactory(event=event, target=target)
    if question_track:
        question.tracks.add(track if question_track == "same" else other_track)
    if question_type:
        question.submission_types.add(
            submission.submission_type if question_type == "same" else other_type
        )

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker, submissions=event.submissions.all(), questions=[question]
        )

    assert missing == ([question] if expected else [])


def test_missing_questions_for_speaker_restricted_questions_follow_matching_submissions():
    event = EventFactory()
    track = TrackFactory(event=event)
    restricted_sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    restricted_sub_q.tracks.add(track)
    restricted_speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    restricted_speaker_q.tracks.add(track)
    unrestricted_speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    matching = SubmissionFactory(event=event, track=track)
    matching.speakers.add(speaker)
    other = SubmissionFactory(event=event, track=TrackFactory(event=event))
    other.speakers.add(speaker)
    AnswerFactory(question=restricted_sub_q, submission=matching, answer="answered")
    submissionless = SpeakerFactory(event=event)
    questions = [restricted_sub_q, restricted_speaker_q, unrestricted_speaker_q]

    with scope(event=event):
        assert missing_questions_for_speaker(
            speaker=speaker, submissions=event.submissions.all(), questions=questions
        ) == [restricted_speaker_q, unrestricted_speaker_q]
        assert missing_questions_for_speaker(
            speaker=submissionless,
            submissions=event.submissions.all(),
            questions=questions,
        ) == [unrestricted_speaker_q]


def test_question_scope_submissions_and_speakers():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    stype = SubmissionTypeFactory(event=event)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    confirmed = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        track=track,
        submission_type=stype,
    )
    track_only = SubmissionFactory(event=event, track=track)
    type_only = SubmissionFactory(event=event, submission_type=stype)
    confirmed_speaker = SpeakerFactory(event=event)
    confirmed.speakers.add(confirmed_speaker)
    submitted_speaker = SpeakerFactory(event=event)
    submitted.speakers.add(submitted_speaker)
    standalone = SpeakerFactory(event=event, user=None, origin="orga")
    SpeakerFactory(event=event, origin="cfp")

    with scope(event=event):
        assert set(question_scope_submissions(event)) == {
            submitted,
            accepted,
            confirmed,
            track_only,
            type_only,
        }
        assert set(question_scope_submissions(event, role="accepted")) == {
            accepted,
            confirmed,
        }
        assert set(question_scope_submissions(event, role="confirmed")) == {confirmed}
        assert list(
            question_scope_submissions(event, track=track, submission_type=stype)
        ) == [confirmed]

        assert set(question_scope_speakers(event)) == {
            confirmed_speaker,
            submitted_speaker,
            standalone,
        }
        talks = question_scope_submissions(event, role="confirmed")
        assert list(question_scope_speakers(event, talks)) == [confirmed_speaker]


@pytest.mark.parametrize(
    ("variant", "answer"),
    (
        (QuestionVariant.STRING, "yes"),
        (QuestionVariant.CHOICES, "Option A"),
        (QuestionVariant.FILE, "file://test.pdf"),
    ),
    ids=("text", "choices", "file"),
)
def test_question_answer_summary_counts_answers_per_variant(variant, answer):
    event = EventFactory()
    question = QuestionFactory(event=event, target="submission", variant=variant)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    SubmissionFactory(event=event)
    created = AnswerFactory(question=question, submission=submission, answer=answer)
    if variant == QuestionVariant.CHOICES:
        created.options.add(AnswerOptionFactory(question=question, answer=answer))

    with scope(event=event):
        info = question_answer_summary(
            question=question,
            talks=event.submissions.all(),
            speakers=question_scope_speakers(event),
        )
        grouped = list(info["grouped_answers"])

    assert info["answer_count"] == 1
    assert info["missing_answers"] == 1
    assert len(grouped) == 1
    assert grouped[0]["count"] == 1
