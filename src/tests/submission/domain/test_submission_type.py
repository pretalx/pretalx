# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.submission.domain.submission_type import propagate_default_duration
from tests.factories import EventFactory, SubmissionFactory, TalkSlotFactory

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
