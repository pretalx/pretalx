# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.submission.domain.submission import (
    apply_invite_addresses,
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
    create_submission,
    make_submitted,
    submit_draft,
)
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
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


def test_create_submission_redeems_access_code():
    event = EventFactory()
    user = UserFactory()
    code = SubmitterAccessCodeFactory(event=event, redeemed=2)

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
    code = SubmitterAccessCodeFactory(event=event, redeemed=2)

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
    code = SubmitterAccessCodeFactory(event=event, redeemed=5)
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


def test_make_submitted_logs_with_orga_and_from_pending_data():
    """A real-state → SUBMITTED transition records previous state, orga
    attribution and the from_pending flag in the log entry's data."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)

    with scope(event=event):
        make_submitted(submission, person=user, orga=True, from_pending=True)
        log = submission.logged_actions().get(
            action_type="pretalx.submission.make_submitted"
        )

    assert submission.state == SubmissionStates.SUBMITTED
    assert log.is_orga_action is True
    assert log.data == {"previous": SubmissionStates.WITHDRAWN, "from_pending": True}


def test_make_submitted_skips_log_when_previous_was_draft():
    """The DRAFT → SUBMITTED transition is the proposal becoming real;
    ``submit_draft`` fires ``pretalx.submission.create`` for that case
    instead, so ``make_submitted`` must stay silent."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    with scope(event=event):
        make_submitted(submission, person=user)
        actions = set(submission.logged_actions().values_list("action_type", flat=True))

    assert submission.state == SubmissionStates.SUBMITTED
    assert "pretalx.submission.make_submitted" not in actions


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
