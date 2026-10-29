# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.person.domain.queries.profile import (
    annotate_speaker_submission_counts,
    annotate_user_submission_counts,
    draft_only_speakers_for_event,
    filter_by_accepted_role,
    filter_reachable,
    other_speaker_profiles,
    speaker_by_email,
    speakers_for_event,
    submitters_for_event,
    visible_talk_slots,
)
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)
from tests.utils import make_published_schedule

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

NON_DRAFT_STATES = (
    SubmissionStates.SUBMITTED,
    SubmissionStates.WITHDRAWN,
    SubmissionStates.REJECTED,
    SubmissionStates.CANCELED,
    SubmissionStates.ACCEPTED,
    SubmissionStates.CONFIRMED,
)


def test_other_speaker_profiles_returns_same_user_profiles_on_other_events():
    user = UserFactory()
    current_event = EventFactory()
    other_event = EventFactory()
    current = SpeakerFactory(user=user, event=current_event, biography="here")
    other = SpeakerFactory(user=user, event=other_event, biography="there")
    SpeakerFactory(user=UserFactory(), event=other_event)

    with scope(event=current_event):
        result = list(other_speaker_profiles(current))

    assert result == [other]


def test_annotate_speaker_submission_counts_counts_per_event():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(speaker)
    rejected = SubmissionFactory(event=event, state="rejected")
    rejected.speakers.add(speaker)

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(pk=speaker.pk),
        event=event,
        submissions=event.submissions.all(),
    )
    result = qs.get()

    assert result.submission_count == 2
    assert result.accepted_submission_count == 1


def test_annotate_user_submission_counts_counts_per_events():
    event = EventFactory()
    user = UserFactory()
    profile = SpeakerFactory(user=user, event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(profile)

    qs = annotate_user_submission_counts(
        User.objects.filter(pk=user.pk), events=[event]
    )
    result = qs.get()

    assert result.submission_count == 1
    assert result.accepted_submission_count == 1


def test_visible_talk_slots_lists_scheduled_slots(event):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        assert list(visible_talk_slots(speaker)) == []

    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    schedule = ScheduleFactory(event=event)
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=event):
        result = list(visible_talk_slots(speaker, schedule=schedule))

    assert result == [slot]


@pytest.mark.parametrize(
    ("attendee_signup", "expect_annotation"),
    ((True, True), (False, False)),
    ids=("feature_on", "feature_off"),
)
def test_visible_talk_slots_annotates_signup_status_per_feature_flag(
    attendee_signup, expect_annotation
):
    event = EventFactory(feature_flags={"attendee_signup": attendee_signup})
    speaker = SpeakerFactory(event=event)
    schedule = ScheduleFactory(event=event)

    with scope(event=event):
        queryset = visible_talk_slots(speaker, schedule=schedule)

    assert (
        "_annotated_signup_status" in queryset.query.annotations
    ) is expect_annotation


@pytest.mark.parametrize(
    ("role", "expected"),
    (
        ("speaker", {"with_accepted"}),
        ("submitter", {"without_accepted"}),
        ("all", {"with_accepted", "without_accepted"}),
        ("", {"with_accepted", "without_accepted"}),
    ),
)
def test_filter_by_accepted_role(role, expected):
    event = EventFactory()
    profiles = {
        "with_accepted": SpeakerFactory(event=event),
        "without_accepted": SpeakerFactory(event=event),
    }
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(profiles["with_accepted"])

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event),
        event=event,
        submissions=event.submissions.all(),
    )
    filtered = set(filter_by_accepted_role(qs, role))

    assert filtered == {profiles[name] for name in expected}


def test_speakers_for_event_returns_distinct_speakers_of_scheduled_talks():
    event = EventFactory()
    [first, second] = make_published_schedule(event, item_count=2)
    with scope(event=event):
        first_speaker = first.speakers.get()
        second_speaker = second.speakers.get()
        second.speakers.add(first_speaker)
        # A speaker with a confirmed but unscheduled submission must not show up.
        unscheduled_speaker = SpeakerFactory(event=event)
        unscheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        unscheduled.speakers.add(unscheduled_speaker)

    with scope(event=event):
        result = list(speakers_for_event(event))

    assert len(result) == 2
    assert set(result) == {first_speaker, second_speaker}


def test_speakers_for_event_no_released_schedule_returns_empty():
    event = EventFactory()
    with scope(event=event):
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub)

    with scope(event=event):
        assert list(speakers_for_event(event)) == []


def test_submitters_for_event_includes_non_draft_submitters_and_optionally_bare_profiles():
    event = EventFactory()
    submitters = set()
    with scope(event=event):
        for state in NON_DRAFT_STATES:
            speaker = SpeakerFactory(event=event)
            SubmissionFactory(event=event, state=state).speakers.add(speaker)
            submitters.add(speaker)
        draft_only = SpeakerFactory(event=event)
        SubmissionFactory(event=event, state=SubmissionStates.DRAFT).speakers.add(
            draft_only
        )
        bare_orga = SpeakerFactory(
            event=event, user=None, origin=SpeakerProfileOrigin.ORGA
        )
        bare_import = SpeakerFactory(
            event=event, user=None, origin=SpeakerProfileOrigin.IMPORT
        )
        SpeakerFactory(event=event, origin=SpeakerProfileOrigin.CFP)

        assert set(submitters_for_event(event)) == submitters
        assert set(submitters_for_event(event, include_bare=True)) == submitters | {
            bare_orga,
            bare_import,
        }


def test_draft_only_speakers_for_event_lists_speakers_with_only_draft_proposals():
    event = EventFactory()
    with scope(event=event):
        draft_only = SpeakerFactory(event=event)
        SubmissionFactory(event=event, state=SubmissionStates.DRAFT).speakers.add(
            draft_only
        )
        SpeakerFactory(event=event)
        for state in NON_DRAFT_STATES:
            speaker = SpeakerFactory(event=event)
            SubmissionFactory(event=event, state=SubmissionStates.DRAFT).speakers.add(
                speaker
            )
            SubmissionFactory(event=event, state=state).speakers.add(speaker)

        assert list(draft_only_speakers_for_event(event)) == [draft_only]


def test_speaker_by_email_matches_contact_then_account_email():
    event = EventFactory()
    with scope(event=event):
        contact = SpeakerFactory(
            event=event,
            user=None,
            email="contact@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
        account_backed = SpeakerFactory(
            event=event,
            email=None,
            user__email="account@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
        both = SpeakerFactory(
            event=event,
            email="both@example.com",
            user__email="both-account@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )

        assert speaker_by_email(event, "Contact@example.com") == contact
        assert speaker_by_email(event, "account@example.com") == account_backed
        assert speaker_by_email(event, "both@example.com") == both
        assert speaker_by_email(event, "both-account@example.com") is None
        assert speaker_by_email(event, "nobody@example.com") is None


def test_speaker_by_email_duplicates_prefer_profile_with_submissions():
    event = EventFactory()
    with scope(event=event):
        first = SpeakerFactory(
            event=event,
            user=None,
            email="shared@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
        with_submission = SpeakerFactory(
            event=event, user=None, email="shared@example.com"
        )
        SubmissionFactory(event=event).speakers.add(with_submission)

        assert speaker_by_email(event, "shared@example.com") == with_submission

        with_submission.submissions.clear()
        assert speaker_by_email(event, "shared@example.com") == first


@pytest.mark.parametrize(
    ("origin", "state", "found"),
    (
        (SpeakerProfileOrigin.CFP, SubmissionStates.SUBMITTED, True),
        (SpeakerProfileOrigin.CFP, SubmissionStates.DRAFT, False),
        (SpeakerProfileOrigin.CFP, None, False),
        (SpeakerProfileOrigin.ORGA, None, True),
        (SpeakerProfileOrigin.IMPORT, None, True),
    ),
)
def test_speaker_by_email_only_finds_visible_profiles(origin, state, found):
    event = EventFactory()
    with scope(event=event):
        profile = SpeakerFactory(
            event=event, user=None, email="contact@example.com", origin=origin
        )
        if state:
            SubmissionFactory(event=event, state=state).speakers.add(profile)

        result = speaker_by_email(event, "Contact@example.com")

    assert result == (profile if found else None)


def test_filter_reachable():
    event = EventFactory()
    with scope(event=event):
        account = SpeakerFactory(event=event, email=None)
        contact_only = SpeakerFactory(
            event=event, user=None, email="contact@example.com"
        )
        SpeakerFactory(event=event, user=None, email=None)
        SpeakerFactory(event=event, user=None, email="")

        result = set(filter_reachable(SpeakerProfile.objects.filter(event=event)))

    assert result == {account, contact_only}
