import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from pretalx.event.actions import build_initial_data
from pretalx.event.models import Event


@pytest.fixture
def event():
    event = Event.objects.create(
        name='Event', slug='event', is_public=True,
        email='orga@orga.org', locale_array='en,de', locale='en',
        date_from=datetime.date.today(), date_to=datetime.date.today()
    )
    build_initial_data(event)
    return event


@pytest.mark.django_db
@pytest.mark.parametrize('locale_array,count', (
    ('de', 1),
    ('de,en', 2),
))
def test_locales(event, locale_array, count):
    event.locale_array = locale_array
    event.save()
    assert len(event.locales) == count
    assert len(event.named_locales) == count


@pytest.mark.parametrize('slug', (
    '_global', '__debug__', 'api', 'csp_report', 'events', 'download',
    'healthcheck', 'jsi18n', 'locale', 'metrics', 'orga', 'redirect',
    'widget',
))
@pytest.mark.django_db
def test_event_model_slug_blacklist_validation(slug):
    with pytest.raises(ValidationError):
        Event(
            name='Event', slug=slug, is_public=True,
            email='orga@orga.org', locale_array='en,de', locale='en',
            date_from=datetime.date.today(), date_to=datetime.date.today()
        ).clean_fields()


@pytest.mark.django_db
def test_event_model_slug_uniqueness():
    Event.objects.create(
        name='Event', slug='slog', is_public=True,
        email='orga@orga.org', locale_array='en,de', locale='en',
        date_from=datetime.date.today(), date_to=datetime.date.today()
    )
    assert Event.objects.count() == 1
    with pytest.raises(IntegrityError):
        Event.objects.create(
            name='Event', slug='slog', is_public=True,
            email='orga@orga.org', locale_array='en,de', locale='en',
            date_from=datetime.date.today(), date_to=datetime.date.today()
        ).clean_fields()


@pytest.mark.django_db
def test_event_urls_custom(event):
    custom = 'https://foo.bar.com'
    assert custom not in event.urls.submit.full()
    event.settings.custom_domain = custom
    assert custom in event.urls.submit.full()
    assert custom not in event.orga_urls.cfp.full()


@pytest.mark.django_db
def test_event_model_talks(slot, other_slot, accepted_submission, submission, rejected_submission):
    event = slot.submission.event
    other_slot.submission.speakers.add(slot.submission.speakers.first())
    assert len(event.talks.all()) == len(set(event.talks.all()))
    assert len(event.speakers.all()) == len(set(event.speakers.all()))
