# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.test import override_settings

from pretalx.common.models.managers import PretalxManager, wrap_manager_class
from pretalx.submission.models import Submission
from tests.factories import SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@override_settings(FETCH_MODE_RAISE=False)
def test_fetch_mode_disabled_allows_lazy_related_access():
    submission = SubmissionFactory()

    fetched = Submission.objects.get(pk=submission.pk)

    assert fetched.event == submission.event


def test_wrap_manager_class_returns_fetch_mode_class_unchanged():
    assert wrap_manager_class(PretalxManager) is PretalxManager
