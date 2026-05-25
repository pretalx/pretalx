# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scope

from pretalx.submission.domain.submission_type import (
    apply_submission_type_field_changes,
    can_delete_submission_type,
    make_default_submission_type,
    propagate_default_duration,
)
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_propagate_default_duration_rewrites_inherited_slots():
    event = EventFactory()
    st = event.cfp.default_type
    submission = SubmissionFactory(event=event, duration=None)
    slot = TalkSlotFactory(submission=submission)

    st.default_duration += 15
    st.save()
    propagate_default_duration(st)

    slot.refresh_from_db()
    assert slot.end == slot.start + dt.timedelta(minutes=st.default_duration)


def test_propagate_default_duration_skips_slots_with_custom_duration():
    event = EventFactory()
    st = event.cfp.default_type
    submission = SubmissionFactory(event=event, duration=45)
    slot = TalkSlotFactory(submission=submission)
    original_end = slot.end

    st.default_duration += 15
    st.save()
    propagate_default_duration(st)

    slot.refresh_from_db()
    assert slot.end == original_end


def test_can_delete_submission_type_true_for_unused():
    event = EventFactory()
    st = SubmissionTypeFactory(event=event)

    with scope(event=event):
        assert can_delete_submission_type(st) is True


def test_can_delete_submission_type_false_for_default():
    event = EventFactory()
    default = event.cfp.default_type

    with scope(event=event):
        assert can_delete_submission_type(default) is False


def test_can_delete_submission_type_false_when_used_by_submission():
    event = EventFactory()
    st = SubmissionTypeFactory(event=event)
    SubmissionFactory(event=event, submission_type=st)

    with scope(event=event):
        assert can_delete_submission_type(st) is False


def test_make_default_submission_type_promotes_and_logs():
    event = EventFactory()
    user = UserFactory()
    new_default = SubmissionTypeFactory(event=event)

    with scope(event=event):
        make_default_submission_type(new_default, person=user)
        event.cfp.refresh_from_db()

        assert event.cfp.default_type == new_default
        log = new_default.logged_actions().first()
        assert log.action_type == "pretalx.submission_type.make_default"
        assert log.person == user


def test_make_default_submission_type_no_op_when_already_default():
    event = EventFactory()
    user = UserFactory()
    default = event.cfp.default_type

    with scope(event=event):
        make_default_submission_type(default, person=user)
        assert not default.logged_actions().exists()


def test_apply_submission_type_field_changes_propagates_duration():
    event = EventFactory()
    st = event.cfp.default_type
    submission = SubmissionFactory(event=event, duration=None)
    slot = TalkSlotFactory(submission=submission)

    st.default_duration += 15
    st.save()
    apply_submission_type_field_changes(st, ["default_duration"])

    slot.refresh_from_db()
    assert slot.end == slot.start + dt.timedelta(minutes=st.default_duration)


@pytest.mark.parametrize(
    ("type_required", "changed_fields", "expect_pinned"),
    (
        (False, ["attendee_signup_required"], True),
        (False, ["name"], False),
        (True, ["attendee_signup_required"], False),
    ),
    ids=(
        "pins_on_signup_unset",
        "no_op_when_field_unchanged",
        "no_op_when_signup_set_to_true",
    ),
)
def test_apply_submission_type_field_changes_signup_cascade(
    type_required, changed_fields, expect_pinned
):
    event = EventFactory()
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = apply_submission_type_field_changes(sub_type, changed_fields)

        submission.refresh_from_db()
    if expect_pinned:
        assert pinned == [submission]
        assert submission.attendee_signup_required is True
    else:
        assert pinned == []
        assert submission.attendee_signup_required is None
