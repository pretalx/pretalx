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
from pretalx.mail.enums import MailTemplateRoles
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
    invite_speaker,
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
from pretalx.submission.models import Answer, Resource, Submission, SubmissionStates
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


def test_create_submission_persists_and_adds_speaker():
    event = EventFactory()
    user = UserFactory()

    with scope(event=event):
        submission = create_submission(
            submission=_build(event), user=user, speakers=[user]
        )

    assert submission.pk is not None
    assert submission.event == event
    assert submission.title == "A talk"
    with scope(event=event):
        assert user in {speaker.user for speaker in submission.speakers.all()}


def test_create_submission_adds_multiple_speakers():
    event = EventFactory()
    creator = UserFactory()
    other = UserFactory()

    with scope(event=event):
        submission = create_submission(
            submission=_build(event), user=creator, speakers=[creator, other]
        )

        assert {s.user for s in submission.speakers.all()} == {creator, other}


def test_create_submission_no_speakers_when_unset():
    """The orga path creates submissions without auto-adding a speaker."""
    event = EventFactory()
    creator = UserFactory()

    with scope(event=event):
        submission = create_submission(submission=_build(event), user=creator)

        assert submission.speakers.count() == 0


def test_create_submission_creator_distinct_from_speakers():
    event = EventFactory()
    creator = UserFactory()
    speaker = UserFactory()

    with scope(event=event):
        submission = create_submission(
            submission=_build(event), user=creator, speakers=[speaker]
        )

        assert speaker in {s.user for s in submission.speakers.all()}
        assert creator not in {s.user for s in submission.speakers.all()}


def test_create_submission_sets_tags():
    event = EventFactory()
    user = UserFactory()
    tag = TagFactory(event=event)

    with scope(event=event):
        submission = create_submission(
            submission=_build(event), user=user, speakers=[user], tags=[tag]
        )

        assert list(submission.tags.all()) == [tag]


def test_create_submission_sends_invitations_for_non_draft(monkeypatch):
    """Non-DRAFT submissions promote ``invite_addresses`` to real
    invitations through ``apply_invite_addresses``."""
    event = EventFactory()
    user = UserFactory()
    sent = []
    monkeypatch.setattr(
        "pretalx.submission.domain.submission.send_invitation",
        lambda submission, *, email, sender: sent.append(email),
    )

    with scope(event=event):
        create_submission(
            submission=_build(event),
            user=user,
            speakers=[user],
            invite_addresses=["a@example.com", "b@example.com"],
        )

    assert sent == ["a@example.com", "b@example.com"]


def test_create_submission_parks_invitations_for_draft(monkeypatch):
    """Drafts park ``invite_addresses`` on ``draft_additional_speakers``
    instead of dispatching them; ``submit_draft`` consumes the parking
    later."""
    event = EventFactory()
    user = UserFactory()
    sent = []
    monkeypatch.setattr(
        "pretalx.submission.domain.submission.send_invitation",
        lambda submission, *, email, sender: sent.append(email),
    )

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, state=SubmissionStates.DRAFT),
            user=user,
            speakers=[user],
            invite_addresses=["a@example.com"],
        )

    assert sent == []
    assert submission.draft_additional_speakers == ["a@example.com"]


def test_create_submission_handles_none_invite_addresses():
    event = EventFactory()
    user = UserFactory()

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, state=SubmissionStates.SUBMITTED),
            user=user,
            speakers=[user],
            invite_addresses=None,
        )

    assert submission.pk is not None
    assert submission.invitations.count() == 0


def test_create_submission_logs_create_for_non_draft():
    event = EventFactory()
    user = UserFactory()

    with scope(event=event):
        submission = create_submission(
            submission=_build(event), user=user, speakers=[user]
        )

    assert (
        submission.logged_actions()
        .filter(action_type="pretalx.submission.create")
        .exists()
    )


def test_create_submission_skips_log_for_draft():
    event = EventFactory()
    user = UserFactory()

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, state=SubmissionStates.DRAFT),
            user=user,
            speakers=[user],
        )

    assert submission.state == SubmissionStates.DRAFT
    # log_action is silenced for DRAFT submissions by Submission.log_action.
    assert (
        not submission.logged_actions()
        .filter(action_type="pretalx.submission.create")
        .exists()
    )


def test_create_submission_fires_state_change_signal_for_non_draft(
    register_signal_handler,
):
    event = EventFactory()
    user = UserFactory()
    received = []
    register_signal_handler(
        submission_state_change,
        lambda signal, sender, **kwargs: received.append(kwargs),
    )

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, state=SubmissionStates.SUBMITTED),
            user=user,
            speakers=[user],
        )

    assert len(received) == 1
    assert received[0]["submission"] == submission
    assert received[0]["old_state"] is None
    assert received[0]["user"] == user


def test_create_submission_skips_state_change_signal_for_draft(register_signal_handler):
    event = EventFactory()
    user = UserFactory()
    received = []
    register_signal_handler(
        submission_state_change,
        lambda signal, sender, **kwargs: received.append(kwargs),
    )

    with scope(event=event):
        create_submission(
            submission=_build(event, state=SubmissionStates.DRAFT),
            user=user,
            speakers=[user],
        )

    assert received == []


@pytest.mark.parametrize(
    ("initial_state", "should_fire"),
    (
        (SubmissionStates.DRAFT, False),
        (SubmissionStates.SUBMITTED, False),
        (SubmissionStates.ACCEPTED, True),
        (SubmissionStates.CONFIRMED, True),
    ),
    ids=["draft", "submitted", "accepted", "confirmed"],
)
def test_create_submission_before_state_change_signal(
    register_signal_handler, initial_state, should_fire
):
    """Non-initial creates (anything other than DRAFT/SUBMITTED) fire the
    veto signal so plugins can refuse them."""
    event = EventFactory()
    user = UserFactory()
    received = []
    register_signal_handler(
        before_submission_state_change,
        lambda signal, sender, **kwargs: received.append(kwargs),
    )

    with scope(event=event):
        create_submission(
            submission=_build(event, state=initial_state), user=user, speakers=[user]
        )

    assert bool(received) is should_fire
    if should_fire:
        assert received[0]["new_state"] == initial_state


def test_create_submission_veto_aborts_persistence(register_signal_handler):
    """A SubmissionError raised from ``before_submission_state_change`` must
    abort ``create_submission`` before the row is written."""
    event = EventFactory()
    user = UserFactory()

    def veto(signal, sender, **kwargs):
        raise SubmissionError("nope")

    register_signal_handler(before_submission_state_change, veto)

    with scope(event=event), pytest.raises(SubmissionError, match="nope"):
        create_submission(
            submission=_build(event, state=SubmissionStates.ACCEPTED),
            user=user,
            speakers=[user],
        )

    with scope(event=event):
        assert not Submission.all_objects.filter(event=event).exists()


def test_create_submission_redeems_access_code():
    event = EventFactory()
    user = UserFactory()
    code = SubmitterAccessCodeFactory(event=event, redeemed=2, maximum_uses=None)

    with scope(event=event):
        submission = create_submission(
            submission=_build(event, access_code=code), user=user, speakers=[user]
        )

    code.refresh_from_db()
    assert submission.access_code == code
    assert code.redeemed == 3


def test_create_submission_does_not_redeem_for_draft():
    """Drafts defer access-code redemption until ``submit_draft``: a draft
    can be abandoned, and the code must stay available until the proposal
    is actually submitted."""
    event = EventFactory()
    user = UserFactory()
    code = SubmitterAccessCodeFactory(event=event, redeemed=2, maximum_uses=None)

    with scope(event=event):
        create_submission(
            submission=_build(event, state=SubmissionStates.DRAFT, access_code=code),
            user=user,
            speakers=[user],
        )

    code.refresh_from_db()
    assert code.redeemed == 2


def test_create_submission_processes_image(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    calls = []
    monkeypatch.setattr(
        Submission, "process_image", lambda self, field: calls.append(field)
    )

    with scope(event=event):
        submission = _build(event)
        submission.image = "fake/path.jpg"  # truthy, no actual file needed
        create_submission(submission=submission, user=user, speakers=[user])

    assert calls == ["image"]


def test_create_submission_skips_image_processing_when_absent(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    calls = []
    monkeypatch.setattr(
        Submission, "process_image", lambda self, field: calls.append(field)
    )

    with scope(event=event):
        create_submission(submission=_build(event), user=user, speakers=[user])

    assert calls == []


def test_create_submission_skips_save_for_already_persisted():
    """Callers that save themselves first (e.g. the API serializer's
    ModelSerializer.create handles M2Ms during save) can still pass the
    saved instance through for the side-effect work."""
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


def test_delete_submission_removes_related():
    submission = SubmissionFactory()
    event = submission.event
    AnswerFactory(question=QuestionFactory(event=event), submission=submission)
    ResourceFactory(submission=submission)
    sub_pk = submission.pk
    with scope(event=event):
        delete_submission(submission)
    assert not Submission.all_objects.filter(pk=sub_pk).exists()
    assert not Answer.objects.filter(submission_id=sub_pk).exists()
    assert not Resource.objects.filter(submission_id=sub_pk).exists()


def test_delete_submission_removes_review_answers():
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
        delete_submission(submission)
    assert not Submission.all_objects.filter(pk=sub_pk).exists()
    assert not Answer.objects.filter(pk=review_answer_pk).exists()


def test_delete_submission_cleans_up_resource_files(django_capture_on_commit_callbacks):
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
        delete_submission(submission)
    assert not resource.resource.storage.exists(file_path)


def test_submit_draft_transitions_state_and_logs():
    """A DRAFT → SUBMITTED transition fires ``pretalx.submission.create``
    (the deferred create log) but NOT ``pretalx.submission.make_submitted``,
    because the proposal is becoming real, not transitioning between two
    real states."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    with scope(event=event):
        submit_draft(submission, user=user)

    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED
    with scope(event=event):
        actions = set(submission.logged_actions().values_list("action_type", flat=True))
    assert "pretalx.submission.create" in actions
    assert "pretalx.submission.make_submitted" not in actions


def test_submit_draft_redeems_access_code():
    """``create_submission`` deferred redemption while the proposal was a
    draft; ``submit_draft`` consumes the code on the way to SUBMITTED."""
    event = EventFactory()
    user = UserFactory()
    code = SubmitterAccessCodeFactory(event=event, redeemed=5, maximum_uses=None)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.DRAFT, access_code=code
    )

    with scope(event=event):
        submit_draft(submission, user=user)

    code.refresh_from_db()
    assert code.redeemed == 6


def test_apply_invite_addresses_parks_for_draft():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    with scope(event=event):
        apply_invite_addresses(
            submission, ["a@example.com", "b@example.com"], sender=user
        )

    submission.refresh_from_db()
    assert submission.draft_additional_speakers == ["a@example.com", "b@example.com"]


def test_apply_invite_addresses_overwrites_previous_parking():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        draft_additional_speakers=["old@example.com"],
    )

    with scope(event=event):
        apply_invite_addresses(submission, ["new@example.com"], sender=user)

    submission.refresh_from_db()
    assert submission.draft_additional_speakers == ["new@example.com"]


def test_apply_invite_addresses_dispatches_for_non_draft(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sent = []
    monkeypatch.setattr(
        "pretalx.submission.domain.submission.send_invitation",
        lambda submission, *, email, sender: sent.append(email),
    )

    with scope(event=event):
        apply_invite_addresses(submission, ["c@example.com"], sender=user)

    assert sent == ["c@example.com"]


def test_apply_invite_addresses_clears_parking_on_dispatch():
    """Switching from DRAFT to a real state must wipe the parking
    field; it has no meaning outside the draft lifecycle."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        draft_additional_speakers=["leftover@example.com"],
    )

    with scope(event=event):
        apply_invite_addresses(submission, [], sender=user)

    submission.refresh_from_db()
    assert submission.draft_additional_speakers == []


def test_apply_invite_addresses_handles_none():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    with scope(event=event):
        apply_invite_addresses(submission, None, sender=user)

    submission.refresh_from_db()
    assert submission.draft_additional_speakers == []


def test_submit_draft_dispatches_invite_addresses(monkeypatch):
    """``submit_draft`` dispatches ``invite_addresses`` as real
    invitations once the proposal has transitioned out of DRAFT."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    sent = []
    monkeypatch.setattr(
        "pretalx.submission.domain.submission.send_invitation",
        lambda submission, *, email, sender: sent.append(email),
    )

    with scope(event=event):
        submit_draft(
            submission, user=user, invite_addresses=["c@example.com", "d@example.com"]
        )

    assert sent == ["c@example.com", "d@example.com"]


def test_submit_draft_clears_leftover_parking(monkeypatch):
    """If the caller passes no addresses, ``submit_draft`` still clears
    any parking from ``draft_additional_speakers`` — the field is only
    meaningful while DRAFT."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.DRAFT,
        draft_additional_speakers=["leftover@example.com"],
    )
    sent = []
    monkeypatch.setattr(
        "pretalx.submission.domain.submission.send_invitation",
        lambda submission, *, email, sender: sent.append(email),
    )

    with scope(event=event):
        submit_draft(submission, user=user)

    assert sent == []
    submission.refresh_from_db()
    assert submission.draft_additional_speakers == []


def test_submit_draft_without_access_code_is_safe():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    with scope(event=event):
        submit_draft(submission, user=user)

    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED


def test_set_submission_state_logs_with_orga_and_from_pending_data():
    """A real-state → SUBMITTED transition records previous state, orga
    attribution and the from_pending flag in the log entry's data."""
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


def test_set_submission_state_skips_log_on_initial_submit_from_draft():
    """The DRAFT → SUBMITTED transition is the proposal becoming real;
    ``submit_draft`` fires ``pretalx.submission.create`` for that case
    instead, so ``set_submission_state`` must stay silent."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    with scope(event=event):
        set_submission_state(submission, SubmissionStates.SUBMITTED, person=user)
        actions = set(submission.logged_actions().values_list("action_type", flat=True))

    assert submission.state == SubmissionStates.SUBMITTED
    assert "pretalx.submission.make_submitted" not in actions


def test_set_pending_state_stores_state_and_reconciles_slots():
    """Pending-accepting a submission creates wip slots for it; the state
    itself stays unchanged until ``apply_pending_state`` runs."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        set_pending_state(submission, SubmissionStates.ACCEPTED)
        submission.refresh_from_db()
        slot_count = event.wip_schedule.talks.filter(submission=submission).count()

    assert submission.state == SubmissionStates.SUBMITTED
    assert submission.pending_state == SubmissionStates.ACCEPTED
    assert slot_count == submission.slot_count


def test_set_pending_state_clear_after_pending_accept_drops_slots():
    """Clearing a pending-accept on a SUBMITTED proposal also removes the
    wip slots that were created while it was pending: slot reconciliation
    follows the queued intent."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        set_pending_state(submission, SubmissionStates.ACCEPTED)
        assert event.wip_schedule.talks.filter(submission=submission).exists()

        set_pending_state(submission, None)
        submission.refresh_from_db()
        slot_count = event.wip_schedule.talks.filter(submission=submission).count()

    assert submission.pending_state is None
    assert slot_count == 0


def test_set_pending_state_clear_resets_to_none():
    """Passing ``None`` clears any queued pending state."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    submission.pending_state = SubmissionStates.ACCEPTED
    submission.save(update_fields=["pending_state"])

    with scope(event=event):
        set_pending_state(submission, None)
        submission.refresh_from_db()

    assert submission.pending_state is None


def test_set_pending_state_pending_accepted_to_rejected_drops_slots():
    """Flipping a pending-accept to pending-reject removes the slots that the
    earlier pending-accept materialised — the queued intent changed direction,
    so the wip schedule has to follow."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        set_pending_state(submission, SubmissionStates.ACCEPTED)
        assert event.wip_schedule.talks.filter(submission=submission).exists()

        set_pending_state(submission, SubmissionStates.REJECTED)
        submission.refresh_from_db()
        slot_count = event.wip_schedule.talks.filter(submission=submission).count()

    assert submission.pending_state == SubmissionStates.REJECTED
    assert slot_count == 0


def test_set_pending_state_skips_reconciliation_outside_accepted_states(
    django_assert_num_queries,
):
    """When neither the previous nor the new pending crosses ``accepted_states``,
    slot existence cannot change (the state alone decides), so we skip the
    reconciliation pass — None → REJECTED on a SUBMITTED proposal should not
    touch the wip schedule at all."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        # Warm caches so we're measuring just the set_pending_state path.
        _ = event.wip_schedule
        with django_assert_num_queries(1):
            # Exactly the pending_state UPDATE, no slot reconciliation queries.
            set_pending_state(submission, SubmissionStates.REJECTED)

    assert submission.pending_state == SubmissionStates.REJECTED


def test_available_tracks_for_submitter_filters_access_code_only():
    event = EventFactory()
    public = TrackFactory(event=event)
    restricted = TrackFactory(event=event, requires_access_code=True)

    with scope(event=event):
        result = set(available_tracks_for_submitter(event))

    assert result == {public}
    assert restricted not in result


def test_available_tracks_for_submitter_with_access_code_returns_its_tracks():
    event = EventFactory()
    code_track = TrackFactory(event=event, requires_access_code=True)
    TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(code_track)

    with scope(event=event):
        result = set(available_tracks_for_submitter(event, access_code=access_code))

    assert result == {code_track}


def test_available_tracks_for_submitter_preserves_instance_track():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    submission.track = TrackFactory(event=event, requires_access_code=True)
    submission.save()

    with scope(event=event):
        result = set(available_tracks_for_submitter(event, instance=submission))

    assert submission.track in result


def test_available_submission_types_locks_when_not_submitted():
    event = EventFactory()
    other = SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    with scope(event=event):
        result = list(
            available_submission_types_for_submitter(event, instance=submission)
        )

    assert result == [submission.submission_type]
    assert other not in result


def test_available_submission_types_locks_when_cfp_closed():
    event = EventFactory()
    event.cfp.deadline = now() - dt.timedelta(days=1)
    event.cfp.save()
    other = SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        result = list(
            available_submission_types_for_submitter(event, instance=submission)
        )

    assert result == [submission.submission_type]
    assert other not in result


def test_available_submission_types_filters_by_per_type_deadline():
    event = EventFactory()
    future = SubmissionTypeFactory(event=event, deadline=now() + dt.timedelta(days=1))
    past = SubmissionTypeFactory(event=event, deadline=now() - dt.timedelta(days=1))

    with scope(event=event):
        result = set(available_submission_types_for_submitter(event))

    assert future in result
    assert past not in result


def test_available_submission_types_with_access_code_returns_its_types():
    event = EventFactory()
    code_type = SubmissionTypeFactory(event=event, requires_access_code=True)
    SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(code_type)

    with scope(event=event):
        result = set(
            available_submission_types_for_submitter(event, access_code=access_code)
        )

    assert result == {code_type}


def test_available_submission_types_preserves_instance_type():
    event = EventFactory()
    custom_type = SubmissionTypeFactory(
        event=event, deadline=now() - dt.timedelta(days=1)
    )
    submission = SubmissionFactory(
        event=event, submission_type=custom_type, state=SubmissionStates.SUBMITTED
    )

    with scope(event=event):
        result = set(
            available_submission_types_for_submitter(event, instance=submission)
        )

    # Even though the type's per-type deadline passed, it stays available so
    # the existing selection survives.
    assert custom_type in result


def test_update_duration():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        update_talk_slots(submission)
        slot = event.wip_schedule.talks.get(submission=submission)
        slot.start = event.datetime_from
        slot.end = event.datetime_from + dt.timedelta(minutes=30)
        slot.save()
        submission.duration = 60
        submission.save()
        update_duration(submission)
        slot.refresh_from_db()
    assert slot.end == slot.start + dt.timedelta(minutes=60)


def test_set_submission_state_noop():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.ACCEPTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    with scope(event=event):
        set_submission_state(submission, SubmissionStates.ACCEPTED)
        submission.refresh_from_db()
    assert submission.pending_state is None


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
    """before_submission_state_change can veto state changes via SubmissionError."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    def veto_handler(signal, sender, **kwargs):
        raise SubmissionError("vetoed")

    register_signal_handler(before_submission_state_change, veto_handler)

    with scope(event=event), pytest.raises(SubmissionError, match="vetoed"):
        set_submission_state(submission, SubmissionStates.ACCEPTED)

    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED


def test_set_submission_state_no_signal_on_initial_submit(register_signal_handler):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    called = []
    register_signal_handler(
        before_submission_state_change,
        lambda signal, sender, **kwargs: called.append(True),
    )

    with scope(event=event):
        set_submission_state(submission, SubmissionStates.SUBMITTED)

    assert submission.state == SubmissionStates.SUBMITTED
    assert called == []


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "rejected", "confirmed", "canceled", "withdrawn"],
)
def test_submission_accept(state):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
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
    with scope(event=event):
        assert event.wip_schedule.talks.filter(submission=submission).exists()


def test_submission_accept_sends_mail_from_submitted():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.accept()
        assert event.queued_mails.count() == mail_count_before + 1


def test_submission_accept_skips_mail_from_confirmed():
    """Un-confirming a talk back to ACCEPTED must not re-queue the
    acceptance mail; the speaker already received it."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.accept()
        assert event.queued_mails.count() == mail_count_before


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "confirmed", "canceled", "withdrawn"],
)
def test_submission_reject(state):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    with scope(event=event):
        submission.reject()

    assert submission.state == SubmissionStates.REJECTED
    with scope(event=event):
        assert not event.wip_schedule.talks.filter(submission=submission).exists()


def test_submission_reject_sends_mail():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.reject()
        assert event.queued_mails.count() == mail_count_before + 1


def test_submission_reject_no_duplicate_mail():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        submission.reject()
        assert event.queued_mails.count() == mail_count_before


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


def test_submission_confirm():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    with scope(event=event):
        submission.confirm()
    assert submission.state == SubmissionStates.CONFIRMED


def test_apply_pending_state_noop():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.SUBMITTED, pending_state=None
    )
    with scope(event=event):
        apply_pending_state(submission)
    assert submission.state == SubmissionStates.SUBMITTED


def test_apply_pending_state_same_as_state():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.ACCEPTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    with scope(event=event):
        apply_pending_state(submission)
    submission.refresh_from_db()
    assert submission.pending_state is None
    assert submission.state == SubmissionStates.ACCEPTED


def test_apply_pending_state_transitions():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    with scope(event=event):
        apply_pending_state(submission)
    assert submission.state == SubmissionStates.ACCEPTED


def test_update_talk_slots_creates_slots():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1


def test_update_talk_slots_deletes_on_reject():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1
        submission.reject()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 0


def test_update_talk_slots_adjusts_count():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1
        submission.slot_count = 3
        submission.save()
        update_talk_slots(submission)
        assert event.wip_schedule.talks.filter(submission=submission).count() == 3


def test_update_talk_slots_reduces_count():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        submission.slot_count = 3
        submission.save()
        update_talk_slots(submission)
        assert event.wip_schedule.talks.filter(submission=submission).count() == 3
        submission.slot_count = 1
        submission.save()
        update_talk_slots(submission)
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1


def test_update_talk_slots_visibility_confirmed():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        submission.confirm()
        slot = event.wip_schedule.talks.get(submission=submission)
    assert slot.is_visible is True


def test_update_talk_slots_visibility_accepted():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    with scope(event=event):
        submission.accept()
        slot = event.wip_schedule.talks.get(submission=submission)
    assert slot.is_visible is False


def test_update_talk_slots_pending_accepted():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    with scope(event=event):
        update_talk_slots(submission)
        assert event.wip_schedule.talks.filter(submission=submission).count() == 1


def test_apply_field_changes_duration():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        update_talk_slots(submission)
        slot = event.wip_schedule.talks.get(submission=submission)
        slot.start = event.datetime_from
        slot.end = event.datetime_from + dt.timedelta(minutes=30)
        slot.save()
        submission.duration = 60
        submission.save()
        apply_field_changes(submission, ["title", "duration"])
        slot.refresh_from_db()
    assert slot.end == slot.start + dt.timedelta(minutes=60)


def test_apply_field_changes_slot_count():
    event = EventFactory()
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, slot_count=2
    )
    with scope(event=event):
        apply_field_changes(submission, {"slot_count"})
        assert event.wip_schedule.talks.filter(submission=submission).count() == 2


def test_apply_field_changes_unrelated_fields_are_noop():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        apply_field_changes(submission, ["title", "abstract"])
        assert event.wip_schedule.talks.filter(submission=submission).count() == 0


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
        scheduled = event.wip_schedule.talks.filter(
            submission=submission, start__isnull=False
        )
    if expect_scheduled:
        slot = scheduled.get()
        assert slot.room == room
        assert slot.start == start
        assert slot.end == end
    else:
        assert not scheduled.exists()


def test_set_wip_slot_clearing_unschedules_existing_slot():
    """A second call with cleared start/room must drop scheduling info even
    after the first call wrote it."""
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
    """Defensive: an accepted submission with no wip slot (shouldn't happen)
    must not crash; the function silently no-ops."""
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
def test_send_state_mail(state, expected):
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=state)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    with scope(event=event):
        mail_count_before = event.queued_mails.count()
        send_state_mail(submission)
        assert event.queued_mails.count() == mail_count_before + expected


def test_collect_content_fields_includes_model_fields():
    submission = SubmissionFactory(
        title="My Talk",
        abstract="An abstract",
        description="A description",
        notes="Some notes",
    )
    fields = dict(_collect_content_fields(submission))
    assert fields["Proposal title"] == "My Talk"
    assert fields["Abstract"] == "An abstract"
    assert fields["Description"] == "A description"
    assert fields["Notes"] == "Some notes"


def test_content_for_mail_placeholder_translates_in_recipient_locale():
    submission = SubmissionFactory(
        title="My Talk", abstract="An abstract", do_not_record=True
    )
    with override("en"):
        result = _content_for_mail_placeholder(submission, locale="de")
    for part in (result.plain, result.html):
        assert "**Zusammenfassung**: An abstract" in part
        assert "**Titel**: My Talk" in part
        assert "**Zeichnet meine Veranstaltung nicht auf.**: Ja" in part
        assert "Abstract" not in part
        assert "Proposal title" not in part


def test_collect_content_fields_prefers_custom_cfp_label():
    submission = SubmissionFactory(
        title="My Talk", abstract="An abstract", description="A description"
    )
    CfPFlow(submission.event).update_field_config(
        "info", "abstract", label="Tell us more"
    )

    fields = dict(_collect_content_fields(submission))
    assert fields["Tell us more"] == "An abstract"
    assert "Abstract" not in fields
    # Fields without a custom label keep their default verbose_name.
    assert fields["Proposal title"] == "My Talk"
    assert fields["Description"] == "A description"


def test_collect_content_fields_custom_cfp_label_uses_recipient_locale():
    """A multilingual custom CfP label resolves to the recipient's email
    locale, not the locale active while the mail is being built."""
    event = EventFactory(locale_array="en,de")
    submission = SubmissionFactory(event=event, abstract="An abstract")
    CfPFlow(event).update_field_config(
        "info", "abstract", label={"en": "Tell us more", "de": "Erzähl mehr"}
    )

    with override("de"):
        assert dict(_collect_content_fields(submission))["Erzähl mehr"] == "An abstract"

    with override("en"):
        result = _content_for_mail_placeholder(submission, locale="de")
    for part in (result.plain, result.html):
        assert "**Erzähl mehr**: An abstract" in part
        assert "Tell us more" not in part
        assert "Abstract" not in part


def test_collect_content_fields_with_boolean_answer():
    submission = SubmissionFactory()
    q = QuestionFactory(event=submission.event, variant="boolean", target="submission")
    AnswerFactory(question=q, answer="True", submission=submission)
    fields = dict(_collect_content_fields(submission))
    assert fields[str(q.question)] == "Yes"


def test_collect_content_fields_with_file_answer():
    submission = SubmissionFactory()
    q = QuestionFactory(event=submission.event, variant="file", target="submission")
    f = SimpleUploadedFile("test.txt", b"content")
    answer = AnswerFactory(question=q, answer_file=f, submission=submission)
    fields = dict(_collect_content_fields(submission))
    assert fields[str(q.question)].endswith(answer.answer_file.url)


@pytest.mark.parametrize("item_count", (1, 3))
def test_collect_content_fields_answers_no_n_plus_one(
    item_count, django_assert_num_queries
):
    submission = SubmissionFactory()
    for _i in range(item_count):
        q = QuestionFactory(event=submission.event, target="submission")
        AnswerFactory(question=q, answer="answer", submission=submission)
    with django_assert_num_queries(1):
        list(_collect_content_fields(submission))


def test_invite_speaker_existing_user():
    submission = SubmissionFactory()
    user = UserFactory()
    speaker = invite_speaker(submission, email=user.email, user=user)
    assert speaker is not None
    assert submission.speakers.filter(pk=speaker.pk).exists()


def test_invite_speaker_new_user():
    submission = SubmissionFactory()
    user = UserFactory()
    speaker = invite_speaker(
        submission, email="newperson@example.com", name="New Person", user=user
    )
    assert speaker is not None
    assert submission.speakers.filter(pk=speaker.pk).exists()


def test_add_speaker():
    submission = SubmissionFactory()
    user = UserFactory()
    speaker = add_speaker(submission, user=user)
    assert submission.speakers.filter(pk=speaker.pk).exists()


def test_add_speaker_sets_position():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    add_speaker(submission, speaker=speaker1)
    add_speaker(submission, speaker=speaker2)
    pos1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1).position
    pos2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2).position
    assert pos2 > pos1


def test_add_speaker_logs_with_user():
    submission = SubmissionFactory()
    log_user = UserFactory()
    target_user = UserFactory()
    add_speaker(submission, user=target_user, log_user=log_user)
    assert (
        submission.logged_actions()
        .filter(action_type="pretalx.submission.speakers.add")
        .exists()
    )


def test_remove_speaker():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)
    remove_speaker(submission, speaker)
    assert not submission.speakers.filter(pk=speaker.pk).exists()


def test_remove_speaker_logs():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)
    remove_speaker(submission, speaker)
    assert (
        submission.logged_actions()
        .filter(action_type="pretalx.submission.speakers.remove")
        .exists()
    )


def test_remove_speaker_nonexistent():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    remove_speaker(submission, speaker)
    assert submission.logged_actions().count() == 0


def test_reorder_speakers():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1)
    submission.speakers.add(speaker2)
    role1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1)
    role2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2)

    reorder_speakers(submission, role_ids=[str(role2.pk), str(role1.pk)])

    assert list(submission.sorted_speakers) == [speaker2, speaker1]


def test_reorder_speakers_logs_change():
    submission = SubmissionFactory()
    user = UserFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1)
    submission.speakers.add(speaker2)
    role1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1)
    role2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2)

    reorder_speakers(submission, role_ids=[str(role2.pk), str(role1.pk)], person=user)

    assert (
        submission.logged_actions()
        .filter(action_type="pretalx.submission.speakers.reorder")
        .exists()
    )


def test_reorder_speakers_noop_does_not_log():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1)
    submission.speakers.add(speaker2)
    role1 = SpeakerRole.objects.get(submission=submission, speaker=speaker1)
    role2 = SpeakerRole.objects.get(submission=submission, speaker=speaker2)
    reorder_speakers(submission, role_ids=[str(role1.pk), str(role2.pk)])
    initial_log_count = submission.logged_actions().count()

    reorder_speakers(submission, role_ids=[str(role1.pk), str(role2.pk)])

    assert submission.logged_actions().count() == initial_log_count


def test_reorder_speakers_unknown_pk_raises_value_error():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    with pytest.raises(ValueError, match="Unknown speaker role"):
        reorder_speakers(submission, role_ids=["9999999"])


def test_send_initial_mails():
    submission = SubmissionFactory()
    event = submission.event
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    submission.speakers.add(speaker)
    djmail.outbox = []
    with scope(event=event):
        send_initial_mails(submission, person=user)
    assert len(djmail.outbox) == 1
    assert user.email in djmail.outbox[0].to


def test_collect_content_fields_with_text_answer():
    submission = SubmissionFactory()
    q = QuestionFactory(event=submission.event, variant="string", target="submission")
    AnswerFactory(question=q, answer="My answer", submission=submission)
    fields = dict(_collect_content_fields(submission))
    assert fields[str(q.question)] == "My answer"


def test_collect_content_fields_with_empty_answer():
    """Text answers with no content show a dash."""
    submission = SubmissionFactory()
    q = QuestionFactory(event=submission.event, variant="string", target="submission")
    AnswerFactory(question=q, answer="", submission=submission)
    fields = dict(_collect_content_fields(submission))
    assert fields[str(q.question)] == "-"


def test_send_initial_mails_with_notification():
    event = EventFactory(mail_settings={"mail_on_new_submission": True})
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    submission.speakers.add(speaker)
    djmail.outbox = []
    with scope(event=event):
        send_initial_mails(submission, person=user)
    assert len(djmail.outbox) == 2


def test_send_initial_mails_template_already_has_content():
    """send_initial_mails doesn't duplicate full_submission_content placeholder."""
    submission = SubmissionFactory()
    event = submission.event
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    submission.speakers.add(speaker)
    with scope(event=event):
        template = mail_template_by_role(event, MailTemplateRoles.NEW_SUBMISSION)
        template.text = str(template.text) + "\n{full_submission_content}"
        template.save()
        original_text = str(template.text)
        send_initial_mails(submission, person=user)
        template.refresh_from_db()
        assert str(template.text) == original_text


def test_pin_signup_required_pins_submission_with_confirmed_signups():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = pin_signup_required(event.submissions.all())

        submission.refresh_from_db()
    assert pinned == [submission]
    assert submission.attendee_signup_required is True


def test_pin_signup_required_skips_submission_without_signups():
    event = EventFactory()
    track = TrackFactory(event=event)
    SubmissionFactory(event=event, track=track)

    with scope(event=event):
        pinned = pin_signup_required(event.submissions.all())

    assert pinned == []


@pytest.mark.parametrize(
    "scenario",
    (
        "explicit_override",
        "type_still_requires",
        "track_still_requires",
        "cancelled_signup",
    ),
)
def test_pin_signup_required_skips_when_not_eligible(scenario):
    event = EventFactory()
    track_required = scenario == "track_still_requires"
    type_required = scenario == "type_still_requires"
    track = TrackFactory(event=event, attendee_signup_required=track_required)
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    submission_kwargs = {"event": event, "track": track, "submission_type": sub_type}
    with scope(event=event):
        if scenario == "explicit_override":
            # Both True and False overrides must be skipped (override wins).
            sub_true = SubmissionFactory(
                **submission_kwargs, attendee_signup_required=True
            )
            sub_false = SubmissionFactory(
                **submission_kwargs, attendee_signup_required=False
            )
            AttendeeSignupFactory(submission=sub_true)
            AttendeeSignupFactory(submission=sub_false)
        else:
            submission = SubmissionFactory(**submission_kwargs)
            signup_state = (
                AttendeeSignupStates.CANCELED
                if scenario == "cancelled_signup"
                else AttendeeSignupStates.CONFIRMED
            )
            AttendeeSignupFactory(submission=submission, state=signup_state)

        pinned = pin_signup_required(event.submissions.all())

    assert pinned == []
    if scenario != "explicit_override":
        submission.refresh_from_db()
        assert submission.attendee_signup_required is None


def test_pin_signup_required_handles_null_track():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event)
    submission = SubmissionFactory(event=event, submission_type=sub_type, track=None)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = pin_signup_required(event.submissions.all())

        submission.refresh_from_db()
    assert pinned == [submission]
    assert submission.attendee_signup_required is True


def test_pin_signup_required_respects_queryset_filter():
    event = EventFactory()
    target_track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    target_submission = SubmissionFactory(event=event, track=target_track)
    other_submission = SubmissionFactory(event=event, track=other_track)
    with scope(event=event):
        AttendeeSignupFactory(submission=target_submission)
        AttendeeSignupFactory(submission=other_submission)

        pinned = pin_signup_required(target_track.submissions.all())

        target_submission.refresh_from_db()
        other_submission.refresh_from_db()
    assert pinned == [target_submission]
    assert target_submission.attendee_signup_required is True
    assert other_submission.attendee_signup_required is None
