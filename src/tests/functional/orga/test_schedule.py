import json
from datetime import datetime

import pytest
import pytz
from django.urls import reverse

from pretalx.schedule.models import Availability, Schedule, TalkSlot


@pytest.mark.django_db
@pytest.mark.usefixtures('room', 'room_availability')
def test_room_list(orga_client, event):
    response = orga_client.get(reverse(f'orga:schedule.api.rooms', kwargs={'event': event.slug}), follow=True)
    content = json.loads(response.content.decode())
    assert response.status_code == 200
    assert len(content['rooms']) == 1
    assert content['rooms'][0]['name']
    assert content['start']
    assert content['end']
    availabilities = content['rooms'][0]['availabilities']
    assert len(availabilities) == 1
    assert availabilities[0]['id'] == 1
    assert availabilities[0]['start']
    assert availabilities[0]['end']


@pytest.mark.django_db
@pytest.mark.usefixtures('accepted_submission')
def test_talk_list(orga_client, event):
    response = orga_client.get(reverse(f'orga:schedule.api.talks', kwargs={'event': event.slug}), follow=True)
    content = json.loads(response.content.decode())
    assert response.status_code == 200
    assert len(content['results']) == 1
    assert content['results'][0]['title']


@pytest.mark.django_db
@pytest.mark.usefixtures('accepted_submission')
def test_api_availabilities(orga_client, event, room, speaker, confirmed_submission):
    talk = TalkSlot.objects.get(submission=confirmed_submission)
    Availability.objects.create(event=event, room=room, start=datetime(2017, 1, 1, 1, tzinfo=pytz.utc), end=datetime(2017, 1, 1, 5, tzinfo=pytz.utc))
    Availability.objects.create(event=event, person=speaker.profiles.first(), start=datetime(2017, 1, 1, 3, tzinfo=pytz.utc), end=datetime(2017, 1, 1, 6, tzinfo=pytz.utc))

    response = orga_client.get(
        reverse(f'orga:schedule.api.availabilities', kwargs={
            'event': event.slug,
            'talkid': talk.pk,
            'roomid': room.pk
        }), follow=True
    )

    content = json.loads(response.content.decode())
    assert response.status_code == 200
    assert len(content['results']) == 1
    assert content['results'][0]['start'] == '2017-01-01 03:00:00+00:00'
    assert content['results'][0]['end'] == '2017-01-01 05:00:00+00:00'


@pytest.mark.django_db
@pytest.mark.usefixtures('accepted_submission')
@pytest.mark.usefixtures('room')
def test_orga_can_see_schedule(orga_client, event):
    response = orga_client.get(event.orga_urls.schedule, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures('accepted_submission')
@pytest.mark.usefixtures('room')
@pytest.mark.xfail
def test_orga_can_release_and_reset_schedule(orga_client, event):
    assert Schedule.objects.count() == 1
    response = orga_client.post(event.orga_urls.release_schedule, follow=True, data={'version': 'Test version 2'})
    assert response.status_code == 200
    assert Schedule.objects.count() == 2
    assert Schedule.objects.get(version='Test version 2')
    response = orga_client.post(event.orga_urls.reset_schedule, follow=True, data={'version': 'Test version 2'})
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures('accepted_submission')
@pytest.mark.usefixtures('room')
def test_orga_cannot_reuse_schedule_name(orga_client, event):
    assert Schedule.objects.count() == 1
    response = orga_client.post(event.orga_urls.release_schedule, follow=True, data={'version': 'Test version 2'})
    assert response.status_code == 200
    assert Schedule.objects.count() == 2
    assert Schedule.objects.get(version='Test version 2')
    response = orga_client.post(event.orga_urls.release_schedule, follow=True, data={'version': 'Test version 2'})
    assert response.status_code == 200
    assert Schedule.objects.count() == 2


@pytest.mark.django_db
def test_orga_can_toggle_schedule_visibility(orga_client, event):
    from pretalx.event.models import Event
    assert event.settings.show_schedule is True

    response = orga_client.get(event.orga_urls.toggle_schedule, follow=True)
    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.settings.show_schedule is False

    response = orga_client.get(event.orga_urls.toggle_schedule, follow=True)
    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.settings.show_schedule is True
# TODO: test talk update view
