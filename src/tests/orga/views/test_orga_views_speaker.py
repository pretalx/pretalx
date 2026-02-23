# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
from unittest.mock import MagicMock

import pytest
from django.contrib.contenttypes.models import ContentType
from django_scopes import scope, scopes_disabled

from pretalx.orga.signals import speaker_form
from pretalx.person.models import SpeakerInformation, SpeakerProfile
from pretalx.submission.models import Answer
from pretalx.submission.models.question import QuestionRequired


@pytest.mark.django_db
@pytest.mark.parametrize("query", ("", "?role=true", "?role=false", "?role=foobar"))
def test_orga_can_access_speakers_list(
    orga_client, speaker, speaker_profile, event, submission, query
):
    response = orga_client.get(event.orga_urls.speakers + query, follow=True)
    assert response.status_code == 200
    if not query:
        assert speaker_profile.get_display_name() in response.text


@pytest.mark.django_db
def test_fulltext_search_finds_speaker_by_biography(
    orga_client, speaker, speaker_profile, event, submission
):
    bio_snippet = speaker_profile.biography[:8]
    # Without fulltext, searching by biography should not find the speaker
    response = orga_client.get(
        event.orga_urls.speakers + f"?q={bio_snippet}", follow=True
    )
    assert response.status_code == 200
    assert speaker_profile.get_display_name() not in response.text
    # With fulltext, it should find the speaker
    response = orga_client.get(
        event.orga_urls.speakers + f"?q={bio_snippet}&fulltext=on", follow=True
    )
    assert response.status_code == 200
    assert speaker_profile.get_display_name() in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_speaker_list_num_queries(
    orga_client,
    event,
    submission,
    other_submission,
    speaker,
    speaker_profile,
    other_speaker,
    django_assert_num_queries,
    item_count,
):
    if item_count != 2:
        with scope(event=event):
            other_profile = SpeakerProfile.objects.get(user=other_speaker, event=event)
            other_profile.user = None
            other_profile.save()
            other_profile.delete()

    with django_assert_num_queries(21):
        response = orga_client.get(event.orga_urls.speakers)
    assert response.status_code == 200
    assert speaker_profile.get_display_name() in response.text


@pytest.mark.django_db
def test_orga_can_access_speaker_page(
    orga_client, speaker_profile, event, submission, django_assert_num_queries
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
    # The history sidebar calls ContentType.objects.get_for_model(), which
    # caches results in memory. Prior tests can populate this cache, saving
    # a query and making the count flaky without this reset.
    ContentType.objects.clear_cache()
    with django_assert_num_queries(22):
        response = orga_client.get(url, follow=True)
    assert response.status_code == 200
    assert speaker_profile.name in response.text


@pytest.mark.django_db
def test_orga_can_change_speaker_password(
    orga_client, speaker, speaker_profile, event, submission
):
    with scope(event=event):
        url = speaker_profile.orga_urls.password_reset
        assert not speaker.pw_reset_token
    response = orga_client.get(url, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert not speaker.pw_reset_token
    response = orga_client.post(url, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.pw_reset_token


@pytest.mark.django_db
def test_reviewer_can_access_speaker_page(
    review_client, speaker_profile, event, submission
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
    response = review_client.get(url, follow=True)
    assert response.status_code == 200
    assert speaker_profile.name in response.text


@pytest.mark.django_db
def test_reviewer_cannot_change_speaker_password(
    review_client, speaker, speaker_profile, event, submission
):
    assert not speaker.pw_reset_token
    with scope(event=event):
        url = speaker_profile.orga_urls.password_reset
    response = review_client.post(url, follow=True)
    assert response.status_code == 404
    with scope(event=event):
        speaker.refresh_from_db()
        assert not speaker.pw_reset_token


@pytest.mark.django_db
def test_orga_can_edit_speaker(
    orga_client, speaker, speaker_profile, event, submission
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
        count = speaker_profile.logged_actions().all().count()
    response = orga_client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": "foo@foooobar.de",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        speaker_profile.refresh_from_db()
        assert count + 1 == speaker_profile.logged_actions().all().count()
    assert speaker_profile.name == "BESTSPEAKAR", response.text
    assert speaker.email == "foo@foooobar.de"


@pytest.mark.django_db
def test_orga_can_edit_speaker_with_custom_field_consolidated_log(
    orga_client, speaker, speaker_profile, event, submission, speaker_question
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
        old_name = speaker_profile.name
        initial_log_count = speaker_profile.logged_actions().count()

    response = orga_client.post(
        url,
        data={
            "name": "Updated Speaker Name",
            "biography": "Updated biography!",
            "email": speaker.email,
            f"question_{speaker_question.pk}": "My speaker answer",
        },
        follow=True,
    )
    assert response.status_code == 200

    with scope(event=event):
        speaker.refresh_from_db()

        logs = speaker_profile.logged_actions()
        new_log_count = logs.count()
        assert new_log_count == initial_log_count + 1
        update_log = logs.filter(action_type="pretalx.user.profile.update").first()
        assert update_log
        assert update_log.changes
        assert update_log.changes["name"]["old"] == old_name
        assert update_log.changes["name"]["new"] == "Updated Speaker Name"
        question_key = f"question-{speaker_question.pk}"
        assert update_log.changes[question_key]["new"] == "My speaker answer"


@pytest.mark.django_db
def test_orga_can_clear_choice_question_answer(
    orga_client, speaker, speaker_profile, event, submission, choice_question
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
        answer = Answer.objects.create(
            question=choice_question, speaker=speaker_profile
        )
        answer.options.set([choice_question.options.first()])
        answer.save()
        assert Answer.objects.filter(pk=answer.pk).exists()

    response = orga_client.post(
        url,
        data={
            "name": speaker_profile.name,
            "biography": speaker_profile.biography,
            "email": speaker.email,
            f"question_{choice_question.pk}": "",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        assert not Answer.objects.filter(pk=answer.pk).exists()


@pytest.mark.django_db
def test_orga_can_edit_speaker_unchanged(
    orga_client, speaker, speaker_profile, event, submission
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
        count = speaker_profile.logged_actions().all().count()
        event.cfp.fields["availabilities"]["visibility"] = "do_not_ask"
        event.cfp.save()
    response = orga_client.post(
        url,
        data={
            "name": speaker_profile.name,
            "biography": speaker_profile.biography,
            "email": speaker.email,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert count == speaker_profile.logged_actions().all().count()


@pytest.mark.django_db
def test_orga_cannot_edit_speaker_without_filling_questions(
    orga_client, speaker, speaker_profile, event, submission, speaker_question
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
        speaker_question.question_required = QuestionRequired.REQUIRED
        speaker_question.save()
    response = orga_client.post(
        url,
        data={"name": "BESTSPEAKAR", "biography": "bio", "email": speaker.email},
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_profile.refresh_from_db()
    assert speaker_profile.name != "BESTSPEAKAR", response.text


@pytest.mark.django_db
def test_orga_cant_assign_duplicate_address(
    orga_client, speaker, speaker_profile, event, submission, other_speaker
):
    with scope(event=event):
        event.cfp.fields["availabilities"]["visibility"] = "do_not_ask"
        event.cfp.save()
    with scope(event=event):
        url = speaker_profile.orga_urls.base
    response = orga_client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": other_speaker.email,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_profile.refresh_from_db()
        speaker.refresh_from_db()
    assert speaker_profile.name != "BESTSPEAKAR", response.text
    assert speaker.email != other_speaker.email


@pytest.mark.django_db
def test_orga_can_edit_speaker_status(orga_client, speaker, event, submission):
    with scopes_disabled():
        logs = speaker.logged_actions().count()
    with scope(event=event):
        assert speaker.profiles.first().has_arrived is False
        url = speaker.profiles.first().orga_urls.toggle_arrived
    response = orga_client.post(url, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.first().has_arrived is True
    with scopes_disabled():
        assert speaker.logged_actions().count() == logs + 1
    response = orga_client.post(url + "?from=list", follow=True)
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.first().has_arrived is False
    with scopes_disabled():
        assert speaker.logged_actions().count() == logs + 2


@pytest.mark.django_db
def test_reviewer_cannot_edit_speaker(
    review_client, speaker, speaker_profile, event, submission
):
    with scope(event=event):
        url = speaker_profile.orga_urls.base
    response = review_client.post(
        url, data={"name": "BESTSPEAKAR", "biography": "I rule!"}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker_profile.refresh_from_db()
    assert speaker_profile.name != "BESTSPEAKAR", response.text


@pytest.mark.django_db
def test_orga_can_sort_speakers_by_question(
    orga_client, event, submission, speaker_question, speaker_answer
):
    response = orga_client.get(
        event.orga_urls.speakers + f"?sort=question_{speaker_question.pk}", follow=True
    )
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_speaker_information_list_num_queries(
    orga_client, event, information, django_assert_num_queries, item_count
):
    if item_count == 2:
        with scope(event=event):
            SpeakerInformation.objects.create(
                event=event, title="Second Info", text="Also important"
            )

    with django_assert_num_queries(20):
        response = orga_client.get(event.orga_urls.information)
    assert response.status_code == 200
    assert information.title in response.text


@pytest.mark.django_db
def test_orga_can_create_speaker_information(orga_client, event):
    with scope(event=event):
        assert event.information.all().count() == 0
    orga_client.post(
        event.orga_urls.new_information,
        data={
            "title_0": "Test Information",
            "text_0": "Very Important!!!",
            "target_group": "submitters",
        },
        follow=True,
    )
    with scope(event=event):
        assert event.information.all().count() == 1


@pytest.mark.django_db
def test_orga_can_edit_speaker_information(orga_client, event, information):
    orga_client.post(
        information.orga_urls.edit,
        data={
            "title_0": "Banana banana",
            "text_0": "Very Important!!!",
            "target_group": "submitters",
        },
        follow=True,
    )
    with scope(event=event):
        information.refresh_from_db()
        assert str(information.title) == "Banana banana"


@pytest.mark.django_db
def test_reviewer_cant_edit_speaker_information(review_client, event, information):
    review_client.post(
        information.orga_urls.edit,
        data={
            "title_0": "Banana banana",
            "text_0": "Very Important!!!",
            "target_group": "confirmed",
        },
        follow=True,
    )
    with scope(event=event):
        information.refresh_from_db()
        assert str(information.title) != "Banana banana"


@pytest.mark.django_db
def test_orga_can_delete_speaker_information(orga_client, event, information):
    with scope(event=event):
        assert event.information.all().count() == 1
    orga_client.post(information.orga_urls.delete, follow=True)
    with scope(event=event):
        assert event.information.all().count() == 0


@pytest.mark.django_db
def test_orga_cant_export_answers_csv_empty(orga_client, speaker, event, submission):
    response = orga_client.post(
        event.orga_urls.speakers + "export/",
        data={"target": "rejected", "name": "on", "export_format": "csv"},
    )
    assert response.status_code == 200
    # HTML response instead of empty download
    assert response.text.strip().lower().startswith("<!doctype")


@pytest.mark.django_db
def test_orga_cant_export_answers_csv_without_delimiter(
    orga_client, speaker, event, submission, answered_choice_question
):
    with scope(event=event):
        answered_choice_question.target = "speaker"
        answered_choice_question.save()
    response = orga_client.post(
        event.orga_urls.speakers + "export/",
        data={
            "target": "all",
            "name": "on",
            f"question_{answered_choice_question.id}": "on",
            "export_format": "csv",
        },
    )
    assert response.status_code == 200
    # HTML response instead of empty download
    assert response.text.strip().lower().startswith("<!doctype")


@pytest.mark.django_db
def test_orga_can_export_answers_csv(
    orga_client, speaker, speaker_profile, event, submission, answered_choice_question
):
    with scope(event=event):
        answered_choice_question.target = "speaker"
        answered_choice_question.save()
        answer = answered_choice_question.answers.all().first().answer_string
    response = orga_client.post(
        event.orga_urls.speakers + "export/",
        data={
            "target": "all",
            "name": "on",
            f"question_{answered_choice_question.id}": "on",
            "submission_ids": "on",
            "export_format": "csv",
            "data_delimiter": "comma",
        },
    )
    assert response.status_code == 200
    assert (
        response.text
        == f"ID,Name,Proposal IDs,{answered_choice_question.question}\r\n{speaker_profile.code},{speaker_profile.get_display_name()},{submission.code},{answer}\r\n"
    )


@pytest.mark.django_db
def test_orga_can_export_answers_json(
    orga_client, speaker, speaker_profile, event, submission, answered_choice_question
):
    with scope(event=event):
        answered_choice_question.target = "speaker"
        answered_choice_question.save()
        answer = answered_choice_question.answers.all().first().answer_string
    response = orga_client.post(
        event.orga_urls.speakers + "export/",
        data={
            "target": "all",
            "name": "on",
            f"question_{answered_choice_question.id}": "on",
            "submission_ids": "on",
            "export_format": "json",
        },
    )
    assert response.status_code == 200
    assert json.loads(response.text) == [
        {
            "ID": speaker_profile.code,
            "Name": speaker_profile.get_display_name(),
            answered_choice_question.question: answer,
            "Proposal IDs": [submission.code],
        }
    ]


@pytest.mark.django_db
def test_track_limited_reviewer_cannot_access_speaker_export(
    review_client, review_user, event, submission, other_submission, track, other_track
):
    with scope(event=event):
        submission.track = track
        submission.save()
        other_submission.track = other_track
        other_submission.save()
        review_user.teams.first().limit_tracks.add(track)

    response = review_client.get(event.orga_urls.speakers + "export/")
    assert response.status_code == 404

    response = review_client.post(
        event.orga_urls.speakers + "export/",
        data={"target": "all", "name": "on", "export_format": "json"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_signal_extra_forms_saved_on_post(
    orga_client, speaker, speaker_profile, event, submission
):

    event.plugins = "tests"
    event.save()

    mock_form = MagicMock()
    mock_form.is_valid.return_value = True

    def signal_receiver(sender, request, **kwargs):
        return mock_form

    speaker_form.connect(signal_receiver)
    try:
        with scope(event=event):
            url = speaker_profile.orga_urls.base

        # GET: extra forms render in context
        response = orga_client.get(url, follow=True)
        assert response.status_code == 200
        assert mock_form in response.context["extra_forms"]

        # POST: extra form must be validated and saved
        response = orga_client.post(
            url,
            data={
                "name": "BESTSPEAKAR",
                "biography": "I rule!",
                "email": speaker.email,
            },
            follow=True,
        )
        assert response.status_code == 200
        mock_form.save.assert_called_once()
    finally:
        speaker_form.disconnect(signal_receiver)
