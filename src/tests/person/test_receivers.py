# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.person.models import ProfilePicture, UserApiToken
from pretalx.person.receivers import clean_orphaned_profile_pictures, run_update_check
from tests.factories import (
    ProfilePictureFactory,
    SpeakerFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_run_update_check_deletes_only_expired_tokens():
    expired = UserApiTokenFactory(expires=now() - dt.timedelta(hours=1))
    active = UserApiTokenFactory(expires=now() + dt.timedelta(hours=1))
    no_expiry = UserApiTokenFactory(expires=None)

    run_update_check(sender=None)

    assert not UserApiToken.objects.filter(pk=expired.pk).exists()
    assert set(UserApiToken.objects.all()) == {active, no_expiry}


def test_clean_orphaned_profile_pictures_deletes_only_old_unreferenced_pictures():
    user = UserFactory()
    old_orphan = ProfilePictureFactory(user=user)
    recent_orphan = ProfilePictureFactory(user=user)
    user_referenced = ProfilePictureFactory(user=user)
    user.profile_picture = user_referenced
    user.save(update_fields=["profile_picture"])
    speaker = SpeakerFactory()
    speaker_referenced = ProfilePictureFactory(user=speaker.user)
    speaker.profile_picture = speaker_referenced
    speaker.save(update_fields=["profile_picture"])
    ProfilePicture.objects.filter(
        pk__in=[old_orphan.pk, user_referenced.pk, speaker_referenced.pk]
    ).update(updated=now() - dt.timedelta(days=31))

    clean_orphaned_profile_pictures(sender=None)

    assert set(ProfilePicture.objects.all()) == {
        recent_orphan,
        user_referenced,
        speaker_referenced,
    }
