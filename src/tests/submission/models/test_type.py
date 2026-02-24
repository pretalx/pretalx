import datetime as dt

import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import SubmitterAccessCode
from pretalx.submission.models.type import SubmissionType, pleasing_number
from tests.factories import (
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    ((1.0, 1), (2.0, 2), (1.5, 1.5), (0.0, 0)),
    ids=["one", "two", "fractional", "zero"],
)
def test_pleasing_number(value, expected):
    assert pleasing_number(value) == expected


@pytest.mark.parametrize(
    ("duration", "expected"),
    (
        (0, "Talk"),
        (30, "Talk (30 minutes)"),
        (60, "Talk (60 minutes)"),
        (90, "Talk (90 minutes)"),
        (100, "Talk (1 hour, 40 minutes)"),
        (120, "Talk (2 hours)"),
        (150, "Talk (2 hours, 30 minutes)"),
        (60 * 24, "Talk (1 day)"),
        (60 * 48, "Talk (2 days)"),
        (60 * 36, "Talk (1.5 days)"),
    ),
)
def test_submission_type_str(duration, expected):
    result = str(SubmissionType(default_duration=duration, name="Talk"))
    assert result == expected


@pytest.mark.django_db
def test_submission_type_log_parent_is_event():
    st = SubmissionTypeFactory()
    assert st.log_parent == st.event


@pytest.mark.django_db
def test_submission_type_log_prefix():
    st = SubmissionTypeFactory()
    assert st.log_prefix == "pretalx.submission_type"


@pytest.mark.django_db
def test_submission_type_slug():
    st = SubmissionTypeFactory(name="Lightning Talk")
    assert st.slug == f"{st.id}-lightning-talk"


@pytest.mark.django_db
def test_submission_type_delete_removes_single_type_access_codes(event):
    """Deleting a type removes access codes that only reference that type."""
    st = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(st)

    with scopes_disabled():
        st.delete()
        assert not SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()


@pytest.mark.django_db
def test_submission_type_delete_keeps_multi_type_access_codes(event):
    """Deleting a type preserves access codes that also reference other types."""
    st1 = SubmissionTypeFactory(event=event)
    st2 = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(st1, st2)

    with scopes_disabled():
        st1.delete()
        assert SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()


@pytest.mark.django_db
def test_submission_type_update_duration_updates_slots(event):
    """update_duration propagates the new default to slots of submissions
    that don't override their duration."""
    with scopes_disabled():
        st = event.cfp.default_type
        submission = SubmissionFactory(event=event, duration=None)
        slot = TalkSlotFactory(submission=submission)

        st.default_duration += 15
        st.save()
        st.update_duration()

        slot.refresh_from_db()
    assert slot.end == slot.start + dt.timedelta(minutes=st.default_duration)


@pytest.mark.django_db
def test_submission_type_update_duration_skips_custom_duration(event):
    """update_duration does not touch submissions with an explicit duration override."""
    with scopes_disabled():
        st = event.cfp.default_type
        submission = SubmissionFactory(event=event, duration=45)
        slot = TalkSlotFactory(submission=submission)
        original_end = slot.end

        st.default_duration += 15
        st.save()
        st.update_duration()

        slot.refresh_from_db()
    assert slot.end == original_end
