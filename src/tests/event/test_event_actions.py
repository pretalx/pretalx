import datetime

import pytest

from pretalx.event.actions import build_initial_data, copy_data_from, shred_organiser
from pretalx.event.models import Event


@pytest.fixture
def raw_event():
    return Event.objects.create(
        name='Event',
        slug='event',
        is_public=True,
        email='orga@orga.org',
        locale_array='en,de',
        locale='en',
        date_from=datetime.date.today(),
        date_to=datetime.date.today(),
    )


@pytest.mark.django_db
def test_initial_data(raw_event):
    event = raw_event
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


@pytest.mark.django_db
@pytest.mark.parametrize('with_url', (True, False))
def test_event_copy_settings(raw_event, submission_type, with_url):
    event = raw_event
    if with_url:
        event.settings.custom_domain = 'https://testeventcopysettings.example.org'
    build_initial_data(event)
    event.settings.random_value = 'testcopysettings'
    event.accept_template.text = 'testtemplate'
    event.accept_template.save()
    new_event = Event.objects.create(
        organiser=event.organiser,
        locale_array='de,en',
        name='Teh Name',
        slug='tn',
        timezone='Europe/Berlin',
        email='tehname@example.org',
        locale='de',
        date_from=datetime.date.today(),
        date_to=datetime.date.today(),
    )
    copy_data_from(event, new_event)
    assert new_event.submission_types.count() == event.submission_types.count()
    assert new_event.accept_template
    assert new_event.accept_template.text == 'testtemplate'
    assert new_event.settings.random_value == 'testcopysettings'
    assert not new_event.settings.custom_domain


@pytest.mark.django_db
def test_shred_used_event(
    resource,
    answered_choice_question,
    personal_answer,
    rejected_submission,
    deleted_submission,
    mail,
    sent_mail,
    room_availability,
    slot,
    unreleased_slot,
    past_slot,
    feedback,
    canceled_talk,
    review,
    information,
    other_event,
):
    assert Event.objects.count() == 2
    shred_organiser(rejected_submission.event.organiser)
    assert Event.objects.count() == 1
