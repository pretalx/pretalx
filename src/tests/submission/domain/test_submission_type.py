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
from pretalx.submission.models import CfP
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_propagate_default_duration_rewrites_only_inherited_slots():
    event = EventFactory()
    st = event.cfp.default_type
    inherited = TalkSlotFactory(
        submission=SubmissionFactory(event=event, duration=None)
    )
    custom = TalkSlotFactory(submission=SubmissionFactory(event=event, duration=45))
    custom_end = custom.end

    st.default_duration += 15
    st.save()
    propagate_default_duration(st)

    inherited.refresh_from_db()
    custom.refresh_from_db()
    assert inherited.end == inherited.start + dt.timedelta(minutes=st.default_duration)
    assert custom.end == custom_end

    st.default_duration += 15
    st.save()
    apply_submission_type_field_changes(st, ["default_duration"])

    inherited.refresh_from_db()
    custom.refresh_from_db()
    assert inherited.end == inherited.start + dt.timedelta(minutes=st.default_duration)
    assert custom.end == custom_end


def test_can_delete_submission_type_unless_default_or_used():
    event = EventFactory()
    st = SubmissionTypeFactory(event=event)

    with scope(event=event):
        assert can_delete_submission_type(st) is True
        assert can_delete_submission_type(event.cfp.default_type) is False
        SubmissionFactory(event=event, submission_type=st)
        assert can_delete_submission_type(st) is False


def test_make_default_submission_type_promotes_and_logs_once():
    event = EventFactory()
    user = UserFactory()
    new_default = SubmissionTypeFactory(event=event)

    with scope(event=event):
        make_default_submission_type(new_default, person=user)
        cfp = CfP.objects.select_related("default_type").get(event=event)

        assert cfp.default_type == new_default
        log = new_default.logged_actions().get()
        assert log.action_type == "pretalx.submission_type.make_default"
        assert log.person == user

        make_default_submission_type(new_default, person=user)
        assert new_default.logged_actions().count() == 1


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
    assert pinned == ([submission] if expect_pinned else [])
    assert submission.attendee_signup_required is (True if expect_pinned else None)
