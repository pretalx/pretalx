import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.common.models.file import CachedFile
from pretalx.event.services import (
    clean_cached_files,
    periodic_event_services,
    task_periodic_event_services,
)
from tests.factories import (
    CachedFileFactory,
    EventFactory,
    ReviewPhaseFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import refresh

pytestmark = pytest.mark.unit

ORGA_MAIL_SUBJECT = "News from your content system"


@pytest.mark.django_db
def test_task_periodic_event_services_nonexistent_slug():
    """Calling with a slug that doesn't exist returns without error."""
    task_periodic_event_services("nonexistent-event-slug")


@pytest.mark.django_db
def test_task_periodic_event_services_sends_cfp_closed_mail(event):
    """When CfP deadline just passed, an orga notification email is sent."""
    djmail.outbox = []
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(hours=1)
        event.cfp.save()

    assert not event.settings.sent_mail_cfp_closed

    task_periodic_event_services(event.slug)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT
    assert event.settings.sent_mail_cfp_closed


@pytest.mark.django_db
def test_task_periodic_event_services_cfp_closed_mail_sent_only_once(event):
    """The CfP closed mail is not re-sent on subsequent runs."""
    djmail.outbox = []
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(hours=1)
        event.cfp.save()

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_task_periodic_event_services_no_cfp_closed_mail_before_deadline(event):
    """No mail is sent when the CfP deadline hasn't passed yet."""
    djmail.outbox = []
    with scope(event=event):
        event.cfp.deadline = now() + dt.timedelta(days=1)
        event.cfp.save()

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_cfp_closed


@pytest.mark.django_db
def test_task_periodic_event_services_no_cfp_closed_mail_after_one_day(event):
    """No CfP-closed mail if the deadline passed more than a day ago."""
    djmail.outbox = []
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(days=2)
        event.cfp.save()

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_cfp_closed


@pytest.mark.django_db
def test_task_periodic_event_services_sends_event_over_mail(event):
    """When an event ended 1-3 days ago and has visible talks, send the
    event-over notification."""
    djmail.outbox = []
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=submission)
        schedule = slot.schedule
        schedule.version = "v1"
        schedule.published = now() - dt.timedelta(days=5)
        schedule.save()
    event.date_from = (now() - dt.timedelta(days=3)).date()
    event.date_to = (now() - dt.timedelta(days=1)).date()
    event.save()

    task_periodic_event_services(event.slug)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT
    assert event.settings.sent_mail_event_over


@pytest.mark.django_db
def test_task_periodic_event_services_event_over_mail_sent_only_once(event):
    """The event-over mail is not re-sent on subsequent runs."""
    djmail.outbox = []
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=submission)
        schedule = slot.schedule
        schedule.version = "v1"
        schedule.published = now() - dt.timedelta(days=5)
        schedule.save()
    event.date_from = (now() - dt.timedelta(days=3)).date()
    event.date_to = (now() - dt.timedelta(days=1)).date()
    event.save()

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_task_periodic_event_services_no_event_over_mail_without_visible_talks(event):
    """No event-over mail when there are no visible talks in the published schedule."""
    djmail.outbox = []
    event.date_from = (now() - dt.timedelta(days=3)).date()
    event.date_to = (now() - dt.timedelta(days=1)).date()
    event.save()

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_event_over


@pytest.mark.django_db
def test_task_periodic_event_services_no_event_over_mail_when_event_too_old(event):
    """No event-over mail if the event ended more than 3 days ago."""
    djmail.outbox = []
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=submission)
        schedule = slot.schedule
        schedule.version = "v1"
        schedule.published = now() - dt.timedelta(days=10)
        schedule.save()
    event.date_from = (now() - dt.timedelta(days=10)).date()
    event.date_to = (now() - dt.timedelta(days=5)).date()
    event.save()

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_event_over


@pytest.mark.django_db
def test_periodic_event_services_updates_review_phases(event):
    """periodic_event_services runs the periodic task (eagerly) and
    updates review phases, deactivating an expired one."""
    with scope(event=event):
        event.review_phases.all().delete()
        expired_phase = ReviewPhaseFactory(
            event=event,
            name="Expired",
            start=now() - dt.timedelta(days=10),
            end=now() - dt.timedelta(days=3),
            is_active=True,
            position=0,
        )

    periodic_event_services(sender=None)

    expired_phase.refresh_from_db()
    assert not expired_phase.is_active


@pytest.mark.django_db
def test_periodic_event_services_skips_old_events():
    """Events that ended more than 3 days ago are not processed."""
    djmail.outbox = []
    with scopes_disabled():
        event = EventFactory(
            date_from=(now() - dt.timedelta(days=10)).date(),
            date_to=(now() - dt.timedelta(days=5)).date(),
        )
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(hours=1)
        event.cfp.save()

    periodic_event_services(sender=None)

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_clean_cached_files_deletes_only_expired():
    """Only expired files are deleted; unexpired files are preserved."""
    expired = CachedFileFactory(expires=now() - dt.timedelta(hours=1))
    not_expired = CachedFileFactory(expires=now() + dt.timedelta(hours=1))

    clean_cached_files(sender=None)

    assert not CachedFile.objects.filter(pk=expired.pk).exists()
    assert CachedFile.objects.filter(pk=not_expired.pk).exists()
