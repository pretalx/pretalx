import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_orga_can_access_speakers_list(orga_client, speaker, event, submission):
    response = orga_client.get(reverse('orga:speakers.list', kwargs={'event': event.slug}), follow=True)
    assert response.status_code == 200
    assert speaker.name in response.content.decode()


@pytest.mark.django_db
def test_orga_can_access_speaker_page(orga_client, speaker, event, submission):
    response = orga_client.get(reverse('orga:speakers.view', kwargs={'event': event.slug, 'pk': speaker.pk}), follow=True)
    assert response.status_code == 200
    assert speaker.name in response.content.decode()


@pytest.mark.django_db
def test_orga_can_edit_speaker(orga_client, speaker, event, submission):
    response = orga_client.post(
        reverse('orga:speakers.edit', kwargs={'event': event.slug, 'pk': speaker.pk}),
        data={'name': 'BESTSPEAKAR', 'biography': 'I rule!'},
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.name == 'BESTSPEAKAR', response.content.decode()
