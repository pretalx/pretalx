# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.domain.queries.user import with_profiles, with_speaker_code
from pretalx.person.models import User
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_with_profiles_prefetches_speakers(event, django_assert_num_queries):
    speaker = SpeakerFactory(event=event)

    users = list(with_profiles(User.objects.all(), event).filter(pk=speaker.user.pk))

    assert len(users) == 1
    with django_assert_num_queries(0):
        speakers = users[0]._speakers
    assert speakers[0].pk == speaker.pk


def test_with_speaker_code_annotates_code(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    users = list(
        with_speaker_code(User.objects.all(), event).filter(pk=speaker.user.pk)
    )

    assert len(users) == 1
    assert users[0].speaker_code == speaker.code


def test_with_speaker_code_no_submissions(event):
    speaker = SpeakerFactory(event=event)

    users = list(
        with_speaker_code(User.objects.all(), event).filter(pk=speaker.user.pk)
    )

    assert len(users) == 1
    assert users[0].speaker_code is None
