import datetime

import pytest

from pretalx.event.actions import build_initial_data
from pretalx.event.models import Event


@pytest.fixture
def event():
    return Event.objects.create(
        name='Event', slug='event', is_public=True,
        email='orga@orga.org', locale_array='en,de', locale='en',
        date_from=datetime.date.today(), date_to=datetime.date.today()
    )


@pytest.mark.django_db
def test_initial_data(event):
    assert not hasattr(event, 'cfp')

    build_initial_data(event)

    assert event.cfp.default_type
    assert event.accept_template
    assert event.ack_template
    assert event.reject_template
    assert event.schedules.count()
    assert event.wip_schedule
    template_count = event.mail_templates.all().count()

    event.cfp.delete()
    build_initial_data(event)

    assert event.cfp
    assert event.cfp.default_type
    assert event.accept_template
    assert event.ack_template
    assert event.reject_template
    assert event.schedules.count()
    assert event.wip_schedule
    assert event.mail_templates.all().count() == template_count
