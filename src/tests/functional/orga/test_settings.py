from datetime import timedelta

import pytest
import json
from django.urls import reverse
from django.utils.timezone import now

from pretalx.event.models import Event
from pretalx.person.models import EventPermission


@pytest.mark.django_db
def test_create_room(orga_client, event, availability):
    assert event.rooms.count() == 0
    response = orga_client.post(
        reverse('orga:settings.rooms.create', kwargs={'event': event.slug}),
        follow=True,
        data={
            'name_0': 'A room',
            'availabilities': json.dumps({
                'availabilities': [
                    {
                        'start': availability.start.strftime('%Y-%m-%d %H:%M:00Z'),
                        'end': availability.end.strftime('%Y-%m-%d %H:%M:00Z'),
                    }
                ]
            })
        }
    )
    assert response.status_code == 200
    assert event.rooms.count() == 1
    assert str(event.rooms.first().name) == 'A room'
    assert event.rooms.first().availabilities.count() == 1
    assert event.rooms.first().availabilities.first().start == availability.start


@pytest.mark.django_db
@pytest.mark.usefixtures('room_availability')
def test_edit_room(orga_client, event, room):
    assert event.rooms.count() == 1
    assert event.rooms.first().availabilities.count() == 1
    assert str(event.rooms.first().name) != 'A room'
    response = orga_client.post(
        reverse('orga:settings.rooms.edit', kwargs={'event': event.slug, 'pk': room.pk}),
        follow=True,
        data={'name_0': 'A room', 'availabilities': '{"availabilities": []}'}
    )
    assert response.status_code == 200
    assert event.rooms.count() == 1
    assert str(event.rooms.first().name) == 'A room'
    assert event.rooms.first().availabilities.count() == 0


@pytest.mark.django_db
def test_delete_room(orga_client, event, room):
    assert event.rooms.count() == 1
    response = orga_client.get(
        reverse('orga:settings.rooms.delete', kwargs={'event': event.slug, 'pk': room.pk}),
        follow=True,
    )
    assert response.status_code == 200
    assert event.rooms.count() == 0


@pytest.mark.django_db
def test_delete_used_room(orga_client, event, room, slot):
    assert event.rooms.count() == 1
    assert slot.room == room
    response = orga_client.get(
        reverse('orga:settings.rooms.delete', kwargs={'event': event.slug, 'pk': room.pk}),
        follow=True,
    )
    assert response.status_code == 200
    assert event.rooms.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('path,allowed', (
    ('tests/functional/orga/fixtures/custom.css', True),
    ('tests/functional/orga/fixtures/malicious.css', False),
    ('tests/functional/conftest.py', False),
))
def test_add_custom_css(event, orga_client, path, allowed):
    assert not event.custom_css
    with open(path, 'r') as custom_css:
        response = orga_client.post(
            event.orga_urls.edit_settings,
            {
                'name_0': event.name,
                'slug': 'csstest',
                'locales': ','.join(event.locales),
                'locale': event.locale,
                'is_public': event.is_public,
                'date_from': event.date_from,
                'date_to': event.date_to,
                'timezone': event.timezone,
                'email': event.email,
                'primary_color': event.primary_color,
                'custom_css': custom_css
            },
            follow=True
        )
    event.refresh_from_db()
    assert response.status_code == 200
    assert bool(event.custom_css) == allowed
    assert (event.slug == 'csstest') == allowed, event.slug


@pytest.mark.django_db
def test_add_logo(event, orga_client):
    assert not event.logo
    response = orga_client.get(event.urls.base, follow=True)
    assert '<img "src="/media' not in response.content.decode()
    with open('../assets/icon.svg', 'rb') as logo:
        response = orga_client.post(
            event.orga_urls.edit_settings,
            {
                'name_0': event.name,
                'slug': 'logotest',
                'locales': event.locales,
                'locale': event.locale,
                'is_public': event.is_public,
                'date_from': event.date_from,
                'date_to': event.date_to,
                'timezone': event.timezone,
                'email': event.email,
                'primary_color': '',
                'custom_css': None,
                'logo': logo,
            },
            follow=True
        )
    event.refresh_from_db()
    assert event.slug == 'logotest', response.content.decode()
    assert response.status_code == 200
    assert event.logo
    response = orga_client.get(event.urls.base, follow=True)
    assert '<img src="/media' in response.content.decode(), response.content.decode()


@pytest.mark.django_db
def test_orga_cannot_create_event(orga_client):
    count = Event.objects.count()
    response = orga_client.post(
        reverse('orga:event.create'),
        {
            'name_0': 'The bestest event',
            'slug': 'testevent',
            'is_public': False,
            'date_from': now().strftime('%Y-%m-%d'),
            'date_to': (now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'timezone': 'UTC',
            'locale': 'en',
            'locales': ['en'],
            'email': 'orga@orga.org',
            'primary_color': None,
        },
        follow=True
    )
    assert response.status_code == 403
    assert not Event.objects.filter(slug='testevent').exists()
    assert Event.objects.count() == count


@pytest.mark.django_db
def test_create_event(superuser_client):
    count = Event.objects.count()
    response = superuser_client.post(
        reverse('orga:event.create'),
        {
            'name_0': 'The bestest event',
            'slug': 'testevent',
            'is_public': False,
            'date_from': now().strftime('%Y-%m-%d'),
            'date_to': (now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'timezone': 'UTC',
            'locale': 'en',
            'locales': ['en'],
            'email': 'orga@orga.org',
            'primary_color': None,
        },
        follow=True
    )
    assert response.status_code == 200, response.content.decode()
    assert Event.objects.get(slug='testevent')
    assert Event.objects.count() == count + 1


@pytest.mark.django_db
def test_save_review_settings(orga_client, event):
    assert event.settings.review_min_score == 0
    assert event.settings.review_max_score == 1
    assert event.settings.review_score_names is None
    response = orga_client.post(
        reverse('orga:settings.review.view', kwargs={'event': event.slug}),
        follow=True,
        data={
            'review_min_score': '0',
            'review_max_score': '2',
            'review_score_name_0': 'OK',
            'review_score_name_1': 'Want',
            'review_score_name_2': 'Super',
        },
    )
    event = Event.objects.get(slug=event.slug)
    assert response.status_code == 200
    assert event.settings.review_min_score == 0
    assert event.settings.review_max_score == 2


@pytest.mark.django_db
def test_save_review_settings_invalid(orga_client, event):
    assert event.settings.review_min_score == 0
    assert event.settings.review_max_score == 1
    assert event.settings.review_score_names is None
    response = orga_client.post(
        reverse('orga:settings.review.view', kwargs={'event': event.slug}),
        follow=True,
        data={
            'review_min_score': '2',
            'review_max_score': '2',
            'review_score_name_0': 'OK',
            'review_score_name_1': 'Want',
            'review_score_name_2': 'Super',
        },
    )
    event = Event.objects.get(slug=event.slug)
    assert response.status_code == 200
    assert event.settings.review_min_score == 0
    assert event.settings.review_max_score == 1


@pytest.mark.django_db
def test_invite_orga_member(orga_client, event):
    assert EventPermission.objects.filter(event=event).count() == 1
    response = orga_client.post(
        event.orga_urls.invite,
        {'email': 'other@user.org'},
        follow=True,
    )
    assert response.status_code == 200
    assert EventPermission.objects.filter(event=event).count() == 2
    perm = EventPermission.objects.get(event=event, invitation_token__isnull=False)
    assert perm.is_orga
    assert not perm.is_reviewer


@pytest.mark.django_db
def test_retract_invitation(orga_client, event):
    assert EventPermission.objects.filter(event=event).count() == 1
    response = orga_client.post(
        event.orga_urls.invite,
        {'email': 'other@user.org'},
        follow=True,
    )
    assert response.status_code == 200
    assert EventPermission.objects.filter(event=event).count() == 2
    perm = EventPermission.objects.get(event=event, invitation_token__isnull=False)
    response = orga_client.post(
        reverse('orga:settings.team.retract', kwargs={'event': event.slug, 'pk': perm.pk}),
        follow=True,
    )
    assert response.status_code == 200
    assert EventPermission.objects.filter(event=event).count() == 1


@pytest.mark.parametrize('target', ('email', 'nick'))
@pytest.mark.django_db
def test_add_orga_to_review(orga_client, event, target):
    perm = EventPermission.objects.get(event=event)
    assert perm.is_reviewer is False
    response = orga_client.post(
        event.orga_urls.invite_reviewer,
        {'nick': getattr(perm.user, target)},
        follow=True,
    )
    assert response.status_code == 200
    perm.refresh_from_db()
    assert perm.is_reviewer is True


@pytest.mark.django_db
def test_invite_new_reviewer(orga_client, event):
    perm = EventPermission.objects.get(event=event)
    assert perm.is_reviewer is False
    response = orga_client.post(
        event.orga_urls.invite_reviewer,
        {'nick': 'new@user_to_be_review.er'},
        follow=True,
    )
    assert response.status_code == 200
    perm.refresh_from_db()
    assert perm.is_reviewer is False
    assert EventPermission.objects.count() == 2
