# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.models import SubmitterAccessCode
from pretalx.submission.models.type import SubmissionType
from tests.factories import (
    EventFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("duration", "expected"),
    (
        (0, ""),
        (None, ""),
        (30, "Default duration: 30\xa0minutes"),
        (100, "Default duration: 1\xa0hour, 40\xa0minutes"),
        (60 * 36, "Default duration: 1\xa0day, 12\xa0hours"),
    ),
)
def test_submission_type_default_duration_display(duration, expected):
    sub_type = SubmissionType(default_duration=duration, name="Talk")
    assert sub_type.default_duration_display == expected


def test_submission_type_str_omits_duration():
    assert str(SubmissionType(default_duration=30, name="Talk")) == "Talk"


@pytest.mark.django_db
def test_submission_type_log_parent_is_event():
    st = SubmissionTypeFactory()
    assert st.log_parent == st.event


@pytest.mark.django_db
def test_submission_type_slug():
    st = SubmissionTypeFactory(name="Lightning Talk")
    assert st.slug == f"{st.id}-lightning-talk"


@pytest.mark.django_db
def test_submission_type_delete_removes_single_type_access_codes():
    event = EventFactory()
    st = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(st)

    st.delete()
    assert not SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()


@pytest.mark.django_db
def test_submission_type_delete_keeps_multi_type_access_codes():
    event = EventFactory()
    st1 = SubmissionTypeFactory(event=event)
    st2 = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(st1, st2)

    st1.delete()
    assert SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()
