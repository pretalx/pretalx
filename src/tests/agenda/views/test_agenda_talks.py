import datetime

import pytest
import pytz
from django.utils import formats


@pytest.mark.django_db
def test_can_see_talk_list(client, django_assert_num_queries, event, slot, other_slot):
    with django_assert_num_queries(18):
        response = client.get(event.urls.talks, follow=True)
    assert response.status_code == 200
    assert slot.submission.title in response.content.decode()


@pytest.mark.django_db
def test_can_see_talk(client, django_assert_num_queries, event, slot, other_slot):
    with django_assert_num_queries(31):
        response = client.get(slot.submission.urls.public, follow=True)
    assert event.schedules.count() == 2
    assert response.status_code == 200
    content = response.content.decode()
    assert content.count(slot.submission.title) >= 2  # meta+h1
    assert slot.submission.abstract in content
    assert slot.submission.description in content
    assert (
        formats.date_format(
            slot.start.astimezone(pytz.timezone(event.timezone)), 'Y-m-d, H:i'
        )
        in content
    )
    assert (
        formats.date_format(slot.end.astimezone(pytz.timezone(event.timezone)), 'H:i')
        in content
    )
    assert str(slot.room.name) in content
    assert 'fa-edit' not in content  # edit btn
    assert 'fa-video' not in content  # do not record


@pytest.mark.django_db
def test_cannot_see_new_talk(client, django_assert_num_queries, event, unreleased_slot):
    slot = unreleased_slot
    with django_assert_num_queries(18):
        response = client.get(slot.submission.urls.public, follow=True)
    assert event.schedules.count() == 1
    assert response.status_code == 404


@pytest.mark.django_db
def test_orga_can_see_new_talk(
    orga_client, django_assert_num_queries, event, unreleased_slot
):
    slot = unreleased_slot
    with django_assert_num_queries(31):
        response = orga_client.get(slot.submission.urls.public, follow=True)
    assert event.schedules.count() == 1
    assert response.status_code == 200
    content = response.content.decode()
    assert content.count(slot.submission.title) >= 2  # meta+h1
    assert slot.submission.abstract in content
    assert slot.submission.description in content
    assert (
        formats.date_format(
            slot.start.astimezone(pytz.timezone(event.timezone)), 'Y-m-d, H:i'
        )
        in content
    )
    assert (
        formats.date_format(slot.end.astimezone(pytz.timezone(event.timezone)), 'H:i')
        in content
    )
    assert str(slot.room.name) in content
    assert 'fa-edit' not in content  # edit btn
    assert 'fa-video' not in content  # do not record


@pytest.mark.django_db
def test_can_see_talk_edit_btn(
    orga_client, django_assert_num_queries, orga_user, event, slot
):
    slot.submission.speakers.add(orga_user)
    with django_assert_num_queries(33):
        response = orga_client.get(slot.submission.urls.public, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'fa-edit' in content  # edit btn
    assert 'fa-video' not in content
    assert 'fa-comments' not in content


@pytest.mark.django_db
def test_can_see_talk_do_not_record(client, django_assert_num_queries, event, slot):
    slot.submission.do_not_record = True
    slot.submission.save()
    with django_assert_num_queries(30):
        response = client.get(slot.submission.urls.public, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'fa-edit' not in content  # edit btn
    assert 'fa-video' in content
    assert 'fa-comments' not in content


@pytest.mark.django_db
def test_can_see_talk_does_accept_feedback(
    client, django_assert_num_queries, event, slot
):
    slot.start = datetime.datetime.now() - datetime.timedelta(days=1)
    slot.end = slot.start + datetime.timedelta(hours=1)
    slot.save()
    with django_assert_num_queries(31):
        response = client.get(slot.submission.urls.public, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'fa-edit' not in content  # edit btn
    assert 'fa-comments' in content
    assert 'fa-video' not in content


@pytest.mark.django_db
def test_cannot_see_nonpublic_talk(client, django_assert_num_queries, event, slot):
    event.is_public = False
    event.save()
    with django_assert_num_queries(23):
        response = client.get(slot.submission.urls.public, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_cannot_see_other_events_talk(
    client, django_assert_num_queries, event, slot, other_event
):
    with django_assert_num_queries(18):
        response = client.get(
            slot.submission.urls.public.replace(event.slug, other_event.slug),
            follow=True,
        )
    assert response.status_code == 404


@pytest.mark.django_db
def test_event_talk_visiblity_submitted(
    client, django_assert_num_queries, event, submission
):
    with django_assert_num_queries(16):
        response = client.get(submission.urls.public, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_event_talk_visiblity_accepted(
    client, django_assert_num_queries, event, slot, accepted_submission
):
    with django_assert_num_queries(17):
        response = client.get(accepted_submission.urls.public, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_event_talk_visiblity_confirmed(
    client, django_assert_num_queries, event, slot, confirmed_submission
):
    with django_assert_num_queries(29):
        response = client.get(confirmed_submission.urls.public, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_event_talk_visiblity_canceled(
    client, django_assert_num_queries, event, slot, canceled_submission
):
    with django_assert_num_queries(17):
        response = client.get(canceled_submission.urls.public, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_event_talk_visiblity_withdrawn(
    client, django_assert_num_queries, event, slot, withdrawn_submission
):
    with django_assert_num_queries(17):
        response = client.get(withdrawn_submission.urls.public, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_speaker_other_submissions(
    client,
    django_assert_num_queries,
    event,
    speaker,
    slot,
    other_slot,
    other_submission,
):
    other_submission.speakers.add(speaker)
    with django_assert_num_queries(34):
        response = client.get(other_submission.urls.public, follow=True)

    assert response.status_code == 200
    assert response.context['speakers']
    assert len(response.context['speakers']) == 2, response.context['speakers']
    speaker_response = [
        s for s in response.context['speakers'] if s.name == speaker.name
    ][0]
    other_response = [
        s for s in response.context['speakers'] if s.name != speaker.name
    ][0]
    assert len(speaker_response.other_submissions) == 1
    assert len(other_response.other_submissions) == 0
    assert (
        speaker_response.other_submissions[0].title
        == speaker.submissions.first().title
    )


@pytest.mark.django_db
def test_talk_speaker_other_submissions_only_if_visible(
    client,
    django_assert_num_queries,
    event,
    speaker,
    slot,
    other_slot,
    other_submission,
):
    other_submission.speakers.add(speaker)
    with django_assert_num_queries(34):
        response = client.get(other_submission.urls.public, follow=True)
    slot.submission.accept(force=True)
    slot.is_visible = False
    slot.save()
    slot.submission.save()

    assert response.status_code == 200
    assert response.context['speakers']
    assert len(response.context['speakers']) == 2, response.context['speakers']
    speaker_response = [
        s for s in response.context['speakers'] if s.name == speaker.name
    ][0]
    other_response = [
        s for s in response.context['speakers'] if s.name != speaker.name
    ][0]
    assert len(speaker_response.other_submissions) == 0
    assert len(other_response.other_submissions) == 0


@pytest.mark.django_db
def test_talk_review_page(
    client, django_assert_num_queries, event, submission, other_submission
):
    with django_assert_num_queries(22):
        response = client.get(submission.urls.review, follow=True)
    assert response.status_code == 200
    assert submission.title in response.content.decode()
