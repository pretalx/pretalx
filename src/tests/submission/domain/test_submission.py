# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django.utils.translation import override
from django_scopes import scope

from pretalx.cfp.flow import CfPFlow
from pretalx.common.exceptions import SubmissionError
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.schedule.domain.changes import has_unreleased_schedule_changes
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.domain.submission import (
    _collect_content_fields,
    _content_for_mail_placeholder,
    add_speaker,
    apply_field_changes,
    apply_invite_addresses,
    apply_pending_state,
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
    create_submission,
    delete_submission,
    notify_speaker_added,
    pin_signup_required,
    remove_speaker,
    reorder_speakers,
    send_initial_mails,
    send_state_mail,
    set_pending_state,
    set_submission_state,
    set_wip_slot,
    submit_draft,
    update_duration,
    update_talk_slots,
)
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import (
    Answer,
    Feedback,
    Resource,
    Submission,
    SubmissionStates,
)
from pretalx.submission.models.question import QuestionTarget
from pretalx.submission.models.submission import SpeakerRole
from pretalx.submission.signals import (
    before_submission_state_change,
    submission_state_change,
)
from tests.factories import (
    AnswerFactory,
    AttendeeSignupFactory,
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _build(event, **overrides):
    fields = {
        "event": event,
        "title": "A talk",
        "submission_type": event.cfp.default_type,
        "abstract": "An abstract",
    }
    fields.update(overrides)
    return Submission(**fields)


def _record_invitations(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "pretalx.submission.domain.submission.send_invitation",
        lambda submission, *, email, sender: sent.append(email),
    )
    return sent


def _record_signal(register_signal_handler, signal):
    received = []
    register_signal_handler(
        signal, lambda signal, sender, **kwargs: received.append(kwargs)
    )
    return received


def test_create_submission_applies_side_effects_for_non_draft(
    monkeypatch, register_signal_handler
):
    event = EventFactory()
    creator = UserFactory()
    speaker = UserFactory()
    other = UserFactory()
    tag = TagFactory(event=event)
    code = SubmitterAccessCodeFactory(event=event, redeemed=2, maximum_uses=None)
    sent = _record_invitations(monkeypatch)
    before = _record_signal(register_signal_handler, before_submission_state_change)
    changed = _record_signal(register_signal_handler, submission_state_change)

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, access_code=code),
            user=creator,
            speakers=[speaker, other],
            tags=[tag],
            invite_addresses=["a@example.com", "b@example.com"],
        )

        assert submission.event == event
        assert submission.title == "A talk"
        assert submission.state == SubmissionStates.SUBMITTED
        assert {s.user for s in submission.speakers.all()} == {speaker, other}
        assert list(submission.tags.all()) == [tag]
        assert submission.access_code == code
        log = submission.logged_actions().get(action_type="pretalx.submission.create")
        assert log.person == creator

    code.refresh_from_db()
    assert code.redeemed == 3
    assert sent == ["a@example.com", "b@example.com"]
    assert before == []
    assert changed == [{"submission": submission, "old_state": None, "user": creator}]

    with scope(event=event):
        bare = create_submission(
            submission=_build(event), user=creator, invite_addresses=None
        )

        assert bare.speakers.count() == 0
        assert bare.invitations.count() == 0


def test_create_submission_defers_side_effects_for_draft(
    monkeypatch, register_signal_handler
):
    event = EventFactory()
    user = UserFactory()
    code = SubmitterAccessCodeFactory(event=event, redeemed=2, maximum_uses=None)
    sent = _record_invitations(monkeypatch)
    before = _record_signal(register_signal_handler, before_submission_state_change)
    changed = _record_signal(register_signal_handler, submission_state_change)

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, state=SubmissionStates.DRAFT, access_code=code),
            user=user,
            speakers=[user],
            invite_addresses=["a@example.com"],
        )

        assert submission.state == SubmissionStates.DRAFT
        assert submission.draft_additional_speakers == ["a@example.com"]
        # log_action is silenced for DRAFT submissions by Submission.log_action.
        assert not submission.logged_actions().exists()

    code.refresh_from_db()
    assert code.redeemed == 2
    assert sent == []
    assert before == []
    assert changed == []


def test_create_submission_fires_before_state_change_for_orga_states(
    register_signal_handler,
):
    event = EventFactory()
    user = UserFactory()
    before = _record_signal(register_signal_handler, before_submission_state_change)

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, state=SubmissionStates.ACCEPTED),
            user=user,
            speakers=[user],
        )

    assert before == [
        {"submission": submission, "new_state": SubmissionStates.ACCEPTED, "user": user}
    ]

    def veto(signal, sender, **kwargs):
        raise SubmissionError("nope")

    register_signal_handler(before_submission_state_change, veto)

    with scope(event=event), pytest.raises(SubmissionError, match="nope"):
        create_submission(
            submission=_build(event, state=SubmissionStates.CONFIRMED),
            user=user,
            speakers=[user],
        )

    with scope(event=event):
        assert list(Submission.all_objects.filter(event=event)) == [submission]


def test_create_submission_processes_image(
    make_image, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    event = EventFactory()
    user = UserFactory()

    with scope(event=event), django_capture_on_commit_callbacks(execute=True):
        submission = _build(event)
        submission.image = make_image("slides.png")
        submission = create_submission(
            submission=submission, user=user, speakers=[user]
        )

    submission.refresh_from_db()
    assert submission.image.name.endswith(".webp")


def test_create_submission_skips_save_for_already_persisted():
    event = EventFactory()
    user = UserFactory()

    with scope(event=event):
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.logged_actions().filter(
            action_type="pretalx.submission.create"
        ).delete()

        result = create_submission(submission=submission, user=user)

        assert result.pk == submission.pk
        assert (
            result.logged_actions()
            .filter(action_type="pretalx.submission.create")
            .exists()
        )


def test_delete_submission_removes_related_rows_and_files(
    django_capture_on_commit_callbacks,
):
    submission = SubmissionFactory()
    event = submission.event
    AnswerFactory(question=QuestionFactory(event=event), submission=submission)
    FeedbackFactory(talk=submission)
    review = ReviewFactory(submission=submission)
    review_answer = AnswerFactory(
        question=QuestionFactory(event=event, target=QuestionTarget.REVIEWER),
        submission=None,
        review=review,
    )
    resource = ResourceFactory(
        submission=submission,
        resource=SimpleUploadedFile("testresource.txt", b"test content"),
        description="Test resource",
    )
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)
    sub_pk = submission.pk

    with scope(event=event), django_capture_on_commit_callbacks(execute=True):
        delete_submission(submission)

    assert not Submission.all_objects.filter(pk=sub_pk).exists()
    assert not Answer.objects.filter(submission_id=sub_pk).exists()
    assert not Answer.objects.filter(pk=review_answer.pk).exists()
    assert not Resource.objects.filter(submission_id=sub_pk).exists()
    assert not Feedback.objects.filter(talk_id=sub_pk).exists()
    assert not resource.resource.storage.exists(file_path)


def test_submit_draft_transitions_redeems_logs_and_invites(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    code = SubmitterAccessCodeFactory(event=event, redeemed=5, maximum_uses=None)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        access_code=code,
        draft_additional_speakers=["leftover@example.com"],
    )
    sent = _record_invitations(monkeypatch)

    with scope(event=event):
        submit_draft(
            submission, user=user, invite_addresses=["c@example.com", "d@example.com"]
        )
        actions = list(
            submission.logged_actions().values_list("action_type", flat=True)
        )

    submission.refresh_from_db(fields=["state", "draft_additional_speakers"])
    assert submission.state == SubmissionStates.SUBMITTED
    assert actions == ["pretalx.submission.create"]
    assert submission.draft_additional_speakers == []
    assert sent == ["c@example.com", "d@example.com"]
    code.refresh_from_db()
    assert code.redeemed == 6

    codeless = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    with scope(event=event):
        submit_draft(codeless, user=user)
    codeless.refresh_from_db(fields=["state"])
    assert codeless.state == SubmissionStates.SUBMITTED
    assert sent == ["c@example.com", "d@example.com"]


def test_apply_invite_addresses_parks_for_draft_and_dispatches_otherwise(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        draft_additional_speakers=["old@example.com"],
    )
    sent = _record_invitations(monkeypatch)

    with scope(event=event):
        apply_invite_addresses(submission, None, sender=user)
        submission.refresh_from_db(fields=["draft_additional_speakers"])
        assert submission.draft_additional_speakers == []

        apply_invite_addresses(
            submission, ["a@example.com", "b@example.com"], sender=user
        )
        submission.refresh_from_db(fields=["draft_additional_speakers"])
        assert submission.draft_additional_speakers == [
            "a@example.com",
            "b@example.com",
        ]

        apply_invite_addresses(submission, ["new@example.com"], sender=user)
        apply_invite_addresses(submission, ["new@example.com"], sender=user)
        submission.refresh_from_db(fields=["draft_additional_speakers"])
        assert submission.draft_additional_speakers == ["new@example.com"]
        assert sent == []

        submission.state = SubmissionStates.SUBMITTED
        submission.save(update_fields=["state"])
        apply_invite_addresses(submission, ["c@example.com"], sender=user)

        submission.refresh_from_db(fields=["draft_additional_speakers"])
        assert sent == ["c@example.com"]
        assert submission.draft_additional_speakers == []


def test_set_submission_state_logs_with_orga_and_from_pending_data():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)

    with scope(event=event):
        set_submission_state(
            submission,
            SubmissionStates.SUBMITTED,
            person=user,
            orga=True,
            from_pending=True,
        )
        log = submission.logged_actions().get(
            action_type="pretalx.submission.make_submitted"
        )

    assert submission.state == SubmissionStates.SUBMITTED
    assert log.is_orga_action is True
    assert log.data == {"previous": SubmissionStates.WITHDRAWN, "from_pending": True}


def test_set_submission_state_initial_submit_skips_log_and_signal(
    register_signal_handler,
):
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    before = _record_signal(register_signal_handler, before_submission_state_change)

    with scope(event=event):
        set_submission_state(submission, SubmissionStates.SUBMITTED, person=user)
        actions = list(
            submission.logged_actions().values_list("action_type", flat=True)
        )

    assert submission.state == SubmissionStates.SUBMITTED
    assert actions == []
    assert before == []


def test_set_pending_state_reconciles_slots_and_refuses_current_state(
    django_assert_num_queries,
):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        talks = event.wip_schedule.talks.filter(submission=submission)

        set_pending_state(submission, SubmissionStates.ACCEPTED)
        submission.refresh_from_db(fields=["state", "pending_state"])
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.ACCEPTED
        assert talks.count() == submission.slot_count == 1

        set_pending_state(submission, SubmissionStates.REJECTED)
        submission.refresh_from_db(fields=["pending_state"])
        assert submission.pending_state == SubmissionStates.REJECTED
        assert talks.count() == 0

        set_pending_state(submission, SubmissionStates.ACCEPTED)
        assert talks.count() == 1

        set_pending_state(submission, None)
        submission.refresh_from_db(fields=["pending_state"])
        assert submission.pending_state is None
        assert talks.count() == 0

        with django_assert_num_queries(1):
            # Exactly the pending_state UPDATE, no slot reconciliation queries.
            set_pending_state(submission, SubmissionStates.REJECTED)

        with pytest.raises(SubmissionError):
            set_pending_state(submission, SubmissionStates.SUBMITTED)

        submission.refresh_from_db(fields=["pending_state"])
        assert submission.pending_state == SubmissionStates.REJECTED


def test_available_tracks_for_submitter():
    event = EventFactory()
    public = TrackFactory(event=event)
    restricted = TrackFactory(event=event, requires_access_code=True)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(restricted)
    submission = SubmissionFactory(event=event, track=restricted)

    with scope(event=event):
        tracks, by_code = available_tracks_for_submitter(event)
        assert (set(tracks), by_code) == ({public}, False)

        tracks, by_code = available_tracks_for_submitter(event, access_code=access_code)
        assert (set(tracks), by_code) == ({restricted}, True)

        tracks, by_code = available_tracks_for_submitter(event, instance=submission)
        assert (set(tracks), by_code) == ({public, restricted}, False)


def test_available_submission_types_for_submitter():
    event = EventFactory()
    default = event.cfp.default_type
    future = SubmissionTypeFactory(event=event, deadline=now() + dt.timedelta(days=1))
    past = SubmissionTypeFactory(event=event, deadline=now() - dt.timedelta(days=1))
    code_type = SubmissionTypeFactory(event=event, requires_access_code=True)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(code_type)
    submission = SubmissionFactory(
        event=event, submission_type=past, state=SubmissionStates.SUBMITTED
    )

    with scope(event=event):
        types, by_code = available_submission_types_for_submitter(event)
        assert (set(types), by_code) == ({default, future}, False)

        types, by_code = available_submission_types_for_submitter(
            event, access_code=access_code
        )
        assert (set(types), by_code) == ({code_type}, True)

        # The instance's own type survives its passed per-type deadline.
        types, by_code = available_submission_types_for_submitter(
            event, instance=submission
        )
        assert (set(types), by_code) == ({default, future, past}, False)

        submission.state = SubmissionStates.ACCEPTED
        submission.save(update_fields=["state"])
        types, by_code = available_submission_types_for_submitter(
            event, instance=submission
        )
        assert (list(types), by_code) == ([past], False)

        submission.state = SubmissionStates.SUBMITTED
        submission.save(update_fields=["state"])
        # The CfP only closes once every per-type deadline has passed as well.
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
        types, by_code = available_submission_types_for_submitter(refresh(event))
        assert (list(types), by_code) == ([future], False)
        event.submission_types.update(deadline=now() - dt.timedelta(days=1))
        types, by_code = available_submission_types_for_submitter(
            refresh(event), instance=submission
        )
        assert (list(types), by_code) == ([past], False)


@pytest.mark.parametrize(
    ("initial_state", "target_state"),
    (
        (SubmissionStates.SUBMITTED, SubmissionStates.REJECTED),
        (SubmissionStates.ACCEPTED, SubmissionStates.CANCELED),
        (SubmissionStates.SUBMITTED, SubmissionStates.WITHDRAWN),
    ),
    ids=["rejected", "canceled", "withdrawn"],
)
def test_set_submission_state_clears_is_featured(initial_state, target_state):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=initial_state, is_featured=True)
    with scope(event=event):
        set_submission_state(submission, target_state)
        submission.refresh_from_db()
    assert submission.is_featured is False


def test_set_submission_state_signal_veto(register_signal_handler):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    def veto_handler(signal, sender, **kwargs):
        raise SubmissionError("vetoed")

    register_signal_handler(before_submission_state_change, veto_handler)

    with scope(event=event), pytest.raises(SubmissionError, match="vetoed"):
        set_submission_state(submission, SubmissionStates.ACCEPTED)

    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.parametrize(
    ("state", "mails"),
    (
        (SubmissionStates.SUBMITTED, 1),
        (SubmissionStates.ACCEPTED, 0),
        (SubmissionStates.REJECTED, 1),
        (SubmissionStates.CONFIRMED, 0),
        (SubmissionStates.CANCELED, 1),
        (SubmissionStates.WITHDRAWN, 1),
    ),
    ids=["submitted", "accepted", "rejected", "confirmed", "canceled", "withdrawn"],
)
def test_submission_accept(state, mails):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    submission.speakers.add(SpeakerFactory(event=event))
    with scope(event=event):
        # The factory creates submissions without materialising wip slots, even
        # when state=ACCEPTED. In production a real ACCEPTED submission would
        # already carry slots from its prior acceptance; seed one here so the
        # no-op branch's "true no-op" semantics are testable independently of
        # the synthetic fixture state.
        if state == SubmissionStates.ACCEPTED:
            event.wip_schedule.talks.create(submission=submission)

        submission.accept()

        assert submission.state == SubmissionStates.ACCEPTED
        assert event.wip_schedule.talks.filter(submission=submission).exists()
        assert event.queued_mails.count() == mails


@pytest.mark.parametrize(
    ("state", "mails"),
    (
        (SubmissionStates.SUBMITTED, 1),
        (SubmissionStates.ACCEPTED, 1),
        (SubmissionStates.CONFIRMED, 1),
        (SubmissionStates.REJECTED, 0),
        (SubmissionStates.CANCELED, 1),
        (SubmissionStates.WITHDRAWN, 1),
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "canceled", "withdrawn"],
)
def test_submission_reject(state, mails):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    submission.speakers.add(SpeakerFactory(event=event))
    with scope(event=event):
        submission.reject()

        assert submission.state == SubmissionStates.REJECTED
        assert not event.wip_schedule.talks.filter(submission=submission).exists()
        assert event.queued_mails.count() == mails


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "canceled"],
)
def test_submission_withdraw(state):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    with scope(event=event):
        submission.withdraw()
    assert submission.state == SubmissionStates.WITHDRAWN
    with scope(event=event):
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.REJECTED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "withdrawn"],
)
def test_submission_cancel(state):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    with scope(event=event):
        submission.cancel()
    assert submission.state == SubmissionStates.CANCELED
    with scope(event=event):
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


def test_apply_pending_state():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.SUBMITTED, pending_state=None
    )
    with scope(event=event):
        apply_pending_state(submission)
        assert submission.state == SubmissionStates.SUBMITTED

        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save(update_fields=["pending_state"])
        apply_pending_state(submission)
        submission.refresh_from_db(fields=["state", "pending_state"])
        assert submission.state == SubmissionStates.ACCEPTED
        assert submission.pending_state is None

        log_count = submission.logged_actions().count()
        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save(update_fields=["pending_state"])
        apply_pending_state(submission)
        submission.refresh_from_db(fields=["state", "pending_state"])
        assert submission.state == SubmissionStates.ACCEPTED
        assert submission.pending_state is None
        assert submission.logged_actions().count() == log_count


def test_set_submission_state_updates_unreleased_changes_flag(
    django_capture_on_commit_callbacks,
):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=1)
    with scope(event=event):
        update_talk_slots(submission)
        set_wip_slot(
            submission, room=room, start=start, end=start + dt.timedelta(minutes=30)
        )
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        assert event.cache.get("has_unreleased_schedule_changes") is False

        with django_capture_on_commit_callbacks(execute=True):
            set_submission_state(submission, SubmissionStates.CANCELED)

        assert has_unreleased_schedule_changes(event) is True


def test_update_talk_slots_follows_state_and_slot_count():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    with scope(event=event):
        talks = event.wip_schedule.talks.filter(submission=submission)

        update_talk_slots(submission)
        assert talks.count() == 1

        submission.accept()
        assert list(talks.values_list("is_visible", flat=True)) == [False]

        submission.confirm()
        assert submission.state == SubmissionStates.CONFIRMED
        assert list(talks.values_list("is_visible", flat=True)) == [True]

        submission.slot_count = 3
        submission.save()
        update_talk_slots(submission)
        assert talks.count() == 3

        submission.slot_count = 1
        submission.save()
        update_talk_slots(submission)
        assert talks.count() == 1

        submission.reject()
        assert talks.count() == 0


def test_apply_field_changes_dispatches_slot_count_and_duration():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, slot_count=2
    )
    with scope(event=event):
        talks = event.wip_schedule.talks.filter(submission=submission)

        apply_field_changes(submission, ["title", "abstract"])
        assert talks.count() == 0

        apply_field_changes(submission, {"slot_count"})
        assert talks.count() == 2

        slot = talks.order_by("pk").first()
        slot.start = event.datetime_from
        slot.end = event.datetime_from + dt.timedelta(minutes=30)
        slot.save()

        submission.duration = 60
        submission.save()
        update_duration(submission)
        slot.refresh_from_db(fields=["end"])
        assert slot.end == slot.start + dt.timedelta(minutes=60)

        submission.duration = 45
        submission.save()
        apply_field_changes(submission, ["title", "duration"])
        slot.refresh_from_db(fields=["end"])
        assert slot.end == slot.start + dt.timedelta(minutes=45)


@pytest.mark.parametrize(
    ("state", "with_room", "with_start", "expect_scheduled"),
    (
        (SubmissionStates.ACCEPTED, True, True, True),
        (SubmissionStates.CONFIRMED, True, True, True),
        (SubmissionStates.SUBMITTED, True, True, False),
        (SubmissionStates.REJECTED, True, True, False),
        (SubmissionStates.CONFIRMED, False, True, False),
        (SubmissionStates.CONFIRMED, True, False, False),
        (SubmissionStates.CONFIRMED, False, False, False),
    ),
    ids=[
        "accepted+room+start",
        "confirmed+room+start",
        "submitted+room+start",
        "rejected+room+start",
        "confirmed+no-room",
        "confirmed+no-start",
        "confirmed+no-room+no-start",
    ],
)
def test_set_wip_slot_paths(state, with_room, with_start, expect_scheduled):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    room = RoomFactory(event=event) if with_room else None
    start = (event.datetime_from + dt.timedelta(hours=1)) if with_start else None
    end = (start + dt.timedelta(minutes=30)) if start else None
    with scope(event=event):
        update_talk_slots(submission)
        set_wip_slot(submission, room=room, start=start, end=end)
        scheduled = [
            (slot.room, slot.start, slot.end)
            for slot in event.wip_schedule.talks.select_related("room").filter(
                submission=submission, start__isnull=False
            )
        ]
    assert scheduled == ([(room, start, end)] if expect_scheduled else [])


def test_set_wip_slot_clearing_unschedules_existing_slot():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=1)
    end = start + dt.timedelta(minutes=30)
    with scope(event=event):
        update_talk_slots(submission)
        set_wip_slot(submission, room=room, start=start, end=end)
        set_wip_slot(submission, room=None, start=None, end=None)
        scheduled = event.wip_schedule.talks.filter(
            submission=submission, start__isnull=False
        ).count()
    assert scheduled == 0


def test_set_wip_slot_no_existing_slot_is_safe():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    start = event.datetime_from + dt.timedelta(hours=1)
    with scope(event=event):
        # Wipe any auto-created slots so the wip queryset is empty.
        submission.slots.filter(schedule=event.wip_schedule).delete()
        set_wip_slot(
            submission, room=room, start=start, end=start + dt.timedelta(minutes=30)
        )
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (SubmissionStates.ACCEPTED, 1),
        (SubmissionStates.REJECTED, 1),
        (SubmissionStates.SUBMITTED, 0),
        (SubmissionStates.CONFIRMED, 0),
        (SubmissionStates.CANCELED, 0),
    ),
    ids=["accepted", "rejected", "submitted", "confirmed", "canceled"],
)
def test_send_state_mail_skips_managed_speakers(state, expected):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    managed = SpeakerFactory(
        event=event, user=None, email="managed@example.com", name="Managed"
    )
    account_backed = SpeakerFactory(event=event)
    submission.speakers.add(managed, account_backed)
    with scope(event=event):
        send_state_mail(submission)

        assert [list(mail.to_speakers.all()) for mail in event.queued_mails.all()] == [
            [account_backed]
        ] * expected


def test_collect_content_fields_lists_model_fields_and_answers(
    django_assert_num_queries,
):
    submission = SubmissionFactory(
        title="My Talk",
        abstract="An abstract",
        description="A description",
        notes="Some notes",
        do_not_record=True,
    )
    event = submission.event
    questions = [
        QuestionFactory(event=event, variant=variant, target="submission", question=q)
        for variant, q in (
            ("boolean", "Bool?"),
            ("file", "File?"),
            ("string", "Text?"),
            ("string", "Empty?"),
        )
    ]
    AnswerFactory(question=questions[0], answer="True", submission=submission)
    file_answer = AnswerFactory(
        question=questions[1],
        answer_file=SimpleUploadedFile("test.txt", b"content"),
        submission=submission,
    )
    AnswerFactory(question=questions[2], answer="My answer", submission=submission)
    AnswerFactory(question=questions[3], answer="", submission=submission)

    with django_assert_num_queries(1):
        fields = list(_collect_content_fields(submission))

    assert fields == [
        ("Proposal title", "My Talk"),
        ("Abstract", "An abstract"),
        ("Description", "A description"),
        ("Notes", "Some notes"),
        ("Language", "en"),
        ("Don’t record this session.", "Yes"),
        ("Bool?", "Yes"),
        ("File?", "http://testserver" + file_answer.answer_file.url),
        ("Text?", "My answer"),
        ("Empty?", "-"),
    ]


def test_content_for_mail_placeholder_uses_custom_labels_in_recipient_locale():
    event = EventFactory(locales=["en", "de"])
    submission = SubmissionFactory(
        event=event, title="My Talk", abstract="An abstract", do_not_record=True
    )
    CfPFlow(submission.event).update_field_config(
        "info", "abstract", label={"en": "Tell us more", "de": "Erzähl mehr"}
    )

    assert list(_collect_content_fields(submission)) == [
        ("Proposal title", "My Talk"),
        ("Tell us more", "An abstract"),
        ("Language", "en"),
        ("Don’t record this session.", "Yes"),
    ]

    with override("en"):
        result = _content_for_mail_placeholder(submission, locale="de")

    expected = (
        "**Titel**: My Talk\n\n**Erzähl mehr**: An abstract\n\n**Sprache**: en\n\n"
        "**Zeichnet meine Veranstaltung nicht auf.**: Ja"
    )
    assert result.plain == expected
    assert result.html == expected


def test_notify_speaker_added_drafts_notification():
    submission = SubmissionFactory()
    existing = SpeakerFactory(event=submission.event)
    djmail.outbox = []

    with scope(event=submission.event):
        add_speaker(submission, existing)
        notify_speaker_added(submission, existing)

        assert len(djmail.outbox) == 0
        mail = submission.event.queued_mails.get()
        assert mail.state == QueuedMailStates.DRAFT
        assert list(mail.to_speakers.all()) == [existing]
        assert "invitation_link" not in str(mail.text)
        assert list(mail.submissions.all()) == [submission]


def test_add_and_remove_speaker_positions_and_logs():
    submission = SubmissionFactory()
    log_user = UserFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    added = submission.logged_actions().filter(
        action_type="pretalx.submission.speakers.add"
    )
    removed = submission.logged_actions().filter(
        action_type="pretalx.submission.speakers.remove"
    )

    remove_speaker(submission, speaker1)
    assert submission.logged_actions().count() == 0

    add_speaker(submission, speaker1)
    add_speaker(submission, speaker2, log_user=log_user)

    assert list(submission.sorted_speakers) == [speaker1, speaker2]
    assert [
        role.position
        for role in SpeakerRole.objects.filter(submission=submission).order_by(
            "position"
        )
    ] == [1, 2]
    assert added.get().person == log_user

    remove_speaker(submission, speaker1)

    assert list(submission.speakers.all()) == [speaker2]
    assert removed.get().data["code"] == speaker1.code


def test_reorder_speakers_logs_changes_and_rejects_unknown_roles():
    submission = SubmissionFactory()
    user = UserFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1)
    submission.speakers.add(speaker2)
    role1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1)
    role2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2)
    logs = submission.logged_actions().filter(
        action_type="pretalx.submission.speakers.reorder"
    )

    reorder_speakers(submission, role_ids=[str(role2.pk), str(role1.pk)], person=user)

    assert list(Submission.objects.get(pk=submission.pk).sorted_speakers) == [
        speaker2,
        speaker1,
    ]
    assert logs.get().person == user

    reorder_speakers(submission, role_ids=[str(role2.pk), str(role1.pk)], person=user)

    assert logs.count() == 1

    with pytest.raises(ValueError, match="Unknown speaker role"):
        reorder_speakers(submission, role_ids=["9999999"])


def test_send_initial_mails_appends_content_placeholder_and_notifies_orga():
    submission = SubmissionFactory()
    event = submission.event
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    submission.speakers.add(speaker)
    djmail.outbox = []

    with scope(event=event):
        send_initial_mails(submission, person=user)

        assert [mail.to for mail in djmail.outbox] == [[user.email]]
        template = mail_template_by_role(event, MailTemplateRoles.NEW_SUBMISSION)
        assert "{full_submission_content}" not in str(template.text)

        template.text = str(template.text) + "\n{full_submission_content}"
        template.save()
        original_text = str(template.text)
        event.mail_settings["mail_on_new_submission"] = True
        event.save()

        send_initial_mails(submission, person=user)

        assert [mail.to for mail in djmail.outbox] == [
            [user.email],
            [user.email],
            [event.email],
        ]
        template.refresh_from_db()
        assert str(template.text) == original_text


def test_pin_signup_required_pins_only_eligible_submissions_in_queryset():
    event = EventFactory()
    target_track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    required_track = TrackFactory(event=event, attendee_signup_required=True)
    required_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    with scope(event=event):
        target = SubmissionFactory(event=event, track=target_track)
        other = SubmissionFactory(event=event, track=other_track)
        trackless = SubmissionFactory(event=event, track=None)
        skipped = {
            "no_signup": SubmissionFactory(event=event, track=other_track),
            "override_true": SubmissionFactory(
                event=event, track=other_track, attendee_signup_required=True
            ),
            "override_false": SubmissionFactory(
                event=event, track=other_track, attendee_signup_required=False
            ),
            "type_requires": SubmissionFactory(
                event=event, track=other_track, submission_type=required_type
            ),
            "track_requires": SubmissionFactory(event=event, track=required_track),
            "cancelled": SubmissionFactory(event=event, track=other_track),
        }
        for submission in (target, other, trackless, *skipped.values()):
            if submission is skipped["no_signup"]:
                continue
            AttendeeSignupFactory(
                submission=submission,
                state=(
                    AttendeeSignupStates.CANCELED
                    if submission is skipped["cancelled"]
                    else AttendeeSignupStates.CONFIRMED
                ),
            )

        assert pin_signup_required(target_track.submissions.all()) == [target]
        assert set(pin_signup_required(event.submissions.all())) == {other, trackless}
        assert pin_signup_required(event.submissions.all()) == []

        pinned = {
            s.code: s.attendee_signup_required
            for s in event.submissions.filter(attendee_signup_required=True)
        }
    assert set(pinned) == {
        target.code,
        other.code,
        trackless.code,
        skipped["override_true"].code,
    }
