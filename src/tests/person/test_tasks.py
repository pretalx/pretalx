import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.person.models import ProfilePicture, UserApiToken
from pretalx.person.tasks import clean_orphaned_profile_pictures, run_update_check
from tests.factories import SpeakerFactory, UserApiTokenFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_run_update_check_deletes_expired_tokens():
    expired = UserApiTokenFactory(expires=now() - dt.timedelta(hours=1))
    active = UserApiTokenFactory(expires=now() + dt.timedelta(hours=1))

    run_update_check(sender=None)

    assert not UserApiToken.objects.filter(pk=expired.pk).exists()
    assert UserApiToken.objects.filter(pk=active.pk).exists()


@pytest.mark.django_db
def test_run_update_check_keeps_tokens_without_expiry():
    no_expiry = UserApiTokenFactory(expires=None)

    run_update_check(sender=None)

    assert UserApiToken.objects.filter(pk=no_expiry.pk).exists()


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_deletes_old_orphan():
    """Orphaned pictures older than 30 days are deleted."""
    user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    ProfilePicture.objects.filter(pk=picture.pk).update(
        updated=now() - dt.timedelta(days=31)
    )

    clean_orphaned_profile_pictures(sender=None)

    assert not ProfilePicture.objects.filter(pk=picture.pk).exists()


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_keeps_recent_orphan():
    """Orphaned pictures less than 30 days old are kept."""
    user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)

    clean_orphaned_profile_pictures(sender=None)

    assert ProfilePicture.objects.filter(pk=picture.pk).exists()


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_keeps_user_referenced():
    """Pictures referenced by a user's profile_picture are not deleted even if old."""
    user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    user.profile_picture = picture
    user.save(update_fields=["profile_picture"])
    ProfilePicture.objects.filter(pk=picture.pk).update(
        updated=now() - dt.timedelta(days=31)
    )

    clean_orphaned_profile_pictures(sender=None)

    assert ProfilePicture.objects.filter(pk=picture.pk).exists()


@pytest.mark.django_db
def test_clean_orphaned_profile_pictures_keeps_speaker_referenced():
    """Pictures referenced by a speaker profile are not deleted even if old."""
    speaker = SpeakerFactory()
    picture = ProfilePicture.objects.create(user=speaker.user)
    speaker.profile_picture = picture
    speaker.save(update_fields=["profile_picture"])
    ProfilePicture.objects.filter(pk=picture.pk).update(
        updated=now() - dt.timedelta(days=31)
    )

    clean_orphaned_profile_pictures(sender=None)

    assert ProfilePicture.objects.filter(pk=picture.pk).exists()
