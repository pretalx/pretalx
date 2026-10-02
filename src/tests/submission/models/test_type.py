# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils import translation
from i18nfield.strings import LazyI18nString

from pretalx.submission.models import SubmitterAccessCode
from pretalx.submission.models.type import SubmissionType
from tests.factories import (
    EventFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("duration", (0, 30, 60, 90, 100, 120, 150, 1440, 2880, 2160))
def test_submission_type_str(duration):
    result = str(SubmissionType(default_duration=duration, name="Talk"))
    assert result == "Talk"


@pytest.mark.parametrize(("locale", "expected"), (("en", "Talk"), ("de", "Vortrag")))
def test_submission_type_str_uses_translated_name(locale, expected):
    submission_type = SubmissionType(
        name=LazyI18nString({"en": "Talk", "de": "Vortrag"}), default_duration=40
    )
    with translation.override(locale):
        assert str(submission_type) == expected


def test_submission_type_str_preserves_manual_suffix_when_duration_changes():
    submission_type = SubmissionType(name="Talk (40 minutes)", default_duration=40)
    submission_type.default_duration = 60
    assert str(submission_type) == "Talk (40 minutes)"


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
