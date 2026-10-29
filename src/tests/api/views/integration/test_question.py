# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django_scopes import scopes_disabled

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.icons import PLATFORM_ICONS
from pretalx.submission.models import Answer, AnswerOption, QuestionVariant
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    CachedFileFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_questionviewset_list_anonymous_sees_public_without_orga_fields(client, event):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            is_public=True,
        )
        QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            is_public=False,
        )
        freeze_schedule(event.wip_schedule, "v1")

    response = client.get(event.api_urls.questions, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert len(content["results"]) == 1
    assert content["results"][0]["question"]["en"] == question.question
    assert "is_visible_to_reviewers" not in content["results"][0]
    assert "contains_personal_data" not in content["results"][0]


def test_questionviewset_list_anonymous_private_event_returns_401(client):
    event = EventFactory(is_public=False)

    response = client.get(event.api_urls.questions, follow=True)

    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_questionviewset_list_organiser_sees_all(
    client, event, orga_read_token, django_assert_num_queries, item_count
):
    with scopes_disabled():
        questions = QuestionFactory.create_batch(
            item_count,
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )

    with django_assert_num_queries(13):
        response = client.get(
            event.api_urls.questions,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200
    assert {r["id"] for r in content["results"]} == {q.id for q in questions}


def test_questionviewset_list_reviewer_sees_visible_questions(
    client, event, review_token
):
    with scopes_disabled():
        visible_q = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            is_visible_to_reviewers=True,
        )

    response = client.get(
        event.api_urls.questions,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert [r["id"] for r in content["results"]] == [visible_q.id]


@pytest.mark.parametrize("target", ("submission", "speaker", "reviewer"))
def test_questionviewset_create_organiser(client, event, orga_write_token, target):
    with scopes_disabled():
        count = event.questions(manager="all_objects").count()

    response = client.post(
        event.api_urls.questions,
        data={
            "question": "A question",
            "variant": "text",
            "target": target,
            "help_text": "hellllp",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["target"] == target
    assert len(response.json()["identifier"]) == 8
    with scopes_disabled():
        assert event.questions(manager="all_objects").count() == count + 1
        q = event.questions(manager="all_objects").first()
        assert q.question == "A question"
        assert q.variant == "text"
        assert q.target == target
        assert q.help_text == "hellllp"
        assert q.identifier == response.json()["identifier"]
        assert q.logged_actions().filter(action_type="pretalx.question.create").exists()


def test_questionviewset_create_with_options(client, event, orga_write_token):
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.post(
        event.api_urls.questions,
        data={
            "question": "A choice question",
            "variant": "choices",
            "target": "submission",
            "identifier": "MY-CUSTOM-ID",
            "options": [{"answer": "Option 1"}, {"answer": "Option 2"}],
        },
        content_type="application/json",
        headers=headers,
    )
    rejected = client.post(
        event.api_urls.questions,
        data={
            "question": "Pick some",
            "variant": "multiple_choice",
            "target": "submission",
            "min_options": 3,
            "options": [{"answer": "First"}, {"answer": "Second"}],
        },
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["identifier"] == "MY-CUSTOM-ID"
    with scopes_disabled():
        q = event.questions(manager="all_objects").get()
        assert q.variant == "choices"
        assert sorted(str(a) for a in q.options.values_list("answer", flat=True)) == [
            "Option 1",
            "Option 2",
        ]
    assert rejected.status_code == 400, rejected.text
    assert rejected.json() == {
        "min_options": [
            "This custom field only has 2 options, so it cannot require 3 of them."
        ]
    }


def test_questionviewset_create_rejected_with_read_token(
    client, event, orga_read_token
):
    other_event = EventFactory()
    headers = {"Authorization": f"Token {orga_read_token.token}"}
    data = {"question": "A question", "variant": "text", "target": "submission"}

    response = client.post(
        event.api_urls.questions,
        data=data,
        content_type="application/json",
        headers=headers,
    )
    other = client.post(
        other_event.api_urls.questions,
        data=data,
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 403, response.text
    assert other.status_code == 403
    with scopes_disabled():
        assert not event.questions(manager="all_objects").exists()
        assert not other_event.questions(manager="all_objects").exists()


@pytest.mark.parametrize("method", ("patch", "put"))
def test_questionviewset_edit_cannot_change_target(
    client, event, orga_write_token, method
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )

    response = getattr(client, method)(
        event.api_urls.questions + f"{question.pk}/",
        data={
            "question": "A question",
            "variant": "number",
            "target": "speaker",
            "help_text": "hellllp",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["target"] == "submission"
    with scopes_disabled():
        question.refresh_from_db()
        assert question.target == "submission"
        assert question.help_text == "hellllp"


def test_questionviewset_edit_options(client, event, orga_write_token, choice_question):
    with scopes_disabled():
        assert choice_question.options.count() == 3

    response = client.patch(
        event.api_urls.questions + f"{choice_question.pk}/",
        data={"options": [{"answer": "Updated Option 1"}, {"answer": "New Option"}]},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        assert sorted(str(o.answer) for o in choice_question.options.all()) == [
            "New Option",
            "Updated Option 1",
        ]


def test_questionviewset_edit_raises_min_options_and_adds_options_at_once(
    client, event, orga_write_token
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.MULTIPLE,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        AnswerOptionFactory(question=question)
        AnswerOptionFactory(question=question)

    response = client.patch(
        event.api_urls.questions + f"{question.pk}/",
        data={
            "min_options": 4,
            "options": [{"answer": f"Option {index}"} for index in range(4)],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        question.refresh_from_db()
        assert question.min_options == 4
        assert question.options.count() == 4


def test_questionviewset_delete_organiser(client, event, orga_write_token):
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target="submission")
        pk = q.pk

    response = client.delete(
        event.api_urls.questions + f"{pk}/",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204, response.text
    with scopes_disabled():
        assert not event.questions(manager="all_objects").filter(pk=pk).exists()
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.question.delete")
            .exists()
        )


def test_questionviewset_delete_with_answers_returns_400(
    client, event, orga_write_token, submission
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        answer = AnswerFactory(question=question, submission=submission, answer="42")
    pk = answer.question.pk

    response = client.delete(
        event.api_urls.questions + f"{pk}/",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    content = response.json()
    assert "answers" in content[0].lower()
    with scopes_disabled():
        assert event.questions(manager="all_objects").filter(pk=pk).exists()


def test_questionviewset_list_filters_and_search(client, event, orga_read_token):
    with scopes_disabled():
        special = QuestionFactory(
            event=event,
            question="Special question",
            variant="text",
            target="submission",
        )
        boolean = QuestionFactory(
            event=event,
            question="Regular question",
            variant="boolean",
            target="submission",
        )
        speaker = QuestionFactory(
            event=event, question="Regular question", variant="text", target="speaker"
        )
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    by_target = client.get(
        event.api_urls.questions + "?target=speaker", headers=headers
    )
    by_variant = client.get(
        event.api_urls.questions + "?variant=boolean", headers=headers
    )
    searched = client.get(event.api_urls.questions + "?q=special", headers=headers)

    assert by_target.status_code == 200
    assert [r["id"] for r in by_target.json()["results"]] == [speaker.pk]
    assert by_variant.status_code == 200
    assert [r["id"] for r in by_variant.json()["results"]] == [boolean.pk]
    assert searched.status_code == 200
    assert [r["id"] for r in searched.json()["results"]] == [special.pk]


def test_questionviewset_expand_options_tracks_submission_types(
    client, event, orga_read_token, choice_question
):
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        choice_question.tracks.add(track)
        choice_question.submission_types.add(sub_type)
        option_count = choice_question.options.count()

    response = client.get(
        event.api_urls.questions
        + f"{choice_question.pk}/?expand=options,tracks,submission_types",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200, response.text
    content = response.json()
    assert len(content["options"]) == option_count
    # Expanded options should not redundantly include the question FK
    assert "question" not in content["options"][0]
    assert content["tracks"][0]["name"]["en"] == track.name
    assert content["submission_types"][0]["name"]["en"] == sub_type.name


@pytest.mark.parametrize(("is_detail", "method"), ((False, "post"), (True, "put")))
def test_questionviewset_question_field_required(
    client, event, orga_write_token, is_detail, method
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )

    url = event.api_urls.questions
    if is_detail:
        url += f"{question.pk}/"

    response = getattr(client, method)(
        url,
        data={},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.data.get("question")[0] == "This field is required."


def test_questionviewset_icon(client, event, orga_read_token):
    with scopes_disabled():
        icon_name = next(iter(PLATFORM_ICONS))
        with_icon = QuestionFactory(
            event=event,
            variant=QuestionVariant.URL,
            target="submission",
            icon=icon_name,
        )
        without_icon = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(
        event.api_urls.questions + f"{with_icon.pk}/icon/", headers=headers
    )
    missing = client.get(
        event.api_urls.questions + f"{without_icon.pk}/icon/", headers=headers
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert "<svg" in response.content.decode()
    assert missing.status_code == 404


def test_answeroptionviewset_read_with_orga_token(
    client, event, orga_read_token, choice_question
):
    with scopes_disabled():
        other_q = QuestionFactory(
            event=event, variant=QuestionVariant.CHOICES, target="submission"
        )
        other_option = AnswerOptionFactory(question=other_q)
        options = list(choice_question.options.order_by("pk"))
        track = TrackFactory(event=event)
        choice_question.tracks.add(track)
    headers = {"Authorization": f"Token {orga_read_token.token}"}
    url = event.api_urls.question_options

    listing = client.get(url, headers=headers)
    filtered = client.get(url + f"?question={choice_question.pk}", headers=headers)
    detail = client.get(url + f"{options[0].pk}/", headers=headers)
    expanded = client.get(
        url + f"?question={choice_question.pk}&expand=question,question.tracks",
        headers=headers,
    )

    assert listing.status_code == 200, listing.text
    assert {o["id"] for o in listing.json()["results"]} == {
        other_option.pk,
        *(o.pk for o in options),
    }
    assert filtered.status_code == 200, filtered.text
    assert {o["id"] for o in filtered.json()["results"]} == {o.pk for o in options}
    assert all(o["question"] == choice_question.pk for o in filtered.json()["results"])
    assert detail.status_code == 200, detail.text
    assert detail.json() == {
        "id": options[0].pk,
        "question": choice_question.pk,
        "answer": {"en": str(options[0].answer)},
        "position": options[0].position,
        "identifier": options[0].identifier,
    }
    assert expanded.status_code == 200, expanded.text
    question_data = expanded.json()["results"][0]["question"]
    assert question_data["id"] == choice_question.pk
    assert [t["name"]["en"] for t in question_data["tracks"]] == [track.name]


def test_answeroptionviewset_create(client, event, orga_write_token, choice_question):
    with scopes_disabled():
        initial_count = choice_question.options.count()
        number_question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.post(
        event.api_urls.question_options,
        data={
            "question": choice_question.pk,
            "answer": {"en": "New API Option"},
            "position": initial_count + 1,
            "identifier": "OPT-CUSTOM",
        },
        content_type="application/json",
        headers=headers,
    )
    rejected = client.post(
        event.api_urls.question_options,
        data={"question": number_question.pk, "answer": {"en": "Invalid Option"}},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201, response.text
    content = response.json()
    assert content["answer"]["en"] == "New API Option"
    assert content["question"] == choice_question.pk
    assert content["identifier"] == "OPT-CUSTOM"
    with scopes_disabled():
        assert choice_question.options.count() == initial_count + 1
    assert rejected.status_code == 400, rejected.text
    assert rejected.json() == {
        "question": [f'Invalid pk "{number_question.pk}" - object does not exist.']
    }


def test_answeroptionviewset_update_and_delete(
    client, event, orga_write_token, choice_question
):
    with scopes_disabled():
        used_option = choice_question.options.first()
        free_option = choice_question.options.last()
        answer = AnswerFactory(question=choice_question, answer=str(used_option.answer))
        answer.options.add(used_option)
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        event.api_urls.question_options + f"{used_option.pk}/",
        data={"answer": {"en": "Updated via API"}},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["answer"]["en"] == "Updated via API"
    with scopes_disabled():
        used_option.refresh_from_db()
        assert str(used_option.answer) == "Updated via API"

    blocked = client.delete(
        event.api_urls.question_options + f"{used_option.pk}/", headers=headers
    )
    deleted = client.delete(
        event.api_urls.question_options + f"{free_option.pk}/", headers=headers
    )

    assert blocked.status_code == 400, blocked.text
    assert deleted.status_code == 204, deleted.text
    with scopes_disabled():
        assert AnswerOption.objects.filter(pk=used_option.pk).exists()
        assert not AnswerOption.objects.filter(pk=free_option.pk).exists()
        assert choice_question.options.count() == 2


def test_answeroptionviewset_reviewer_sees_visible_options(client, event, review_token):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.CHOICES,
        target="speaker",
        is_visible_to_reviewers=True,
    )
    option = AnswerOptionFactory(question=question)

    response = client.get(
        event.api_urls.question_options,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200
    assert [o["id"] for o in response.json()["results"]] == [option.pk]


def test_answeroptionviewset_anonymous_sees_public_question_options(client, event):
    with scopes_disabled():
        public_question = QuestionFactory(
            event=event,
            variant=QuestionVariant.CHOICES,
            target="speaker",
            is_public=True,
        )
        public_options = AnswerOptionFactory.create_batch(3, question=public_question)
        private_question = QuestionFactory(
            event=event,
            variant=QuestionVariant.CHOICES,
            target="speaker",
            is_public=False,
        )
        AnswerOptionFactory(question=private_question)
        freeze_schedule(event.wip_schedule, "v1")

    response = client.get(event.api_urls.question_options)

    assert response.status_code == 200, response.text
    assert {o["id"] for o in response.json()["results"]} == {
        o.pk for o in public_options
    }


def test_answerviewset_list_anonymous_returns_401(client, event, submission):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
    )
    AnswerFactory(question=question, submission=submission, answer="42")

    response = client.get(event.api_urls.answers, follow=True)

    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.parametrize(
    ("expand", "expected_queries"),
    (("", 13), ("question", 15), ("question.tracks", 15)),
)
def test_answerviewset_list_organiser(
    client,
    event,
    orga_read_token,
    submission,
    django_assert_num_queries,
    item_count,
    expand,
    expected_queries,
):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
    )
    AnswerFactory(question=question, submission=submission, answer="42")
    for _ in range(1, item_count):
        with scopes_disabled():
            AnswerFactory(
                question=question, submission=submission, answer="second answer"
            )

    with django_assert_num_queries(expected_queries):
        response = client.get(
            event.api_urls.answers + f"?expand={expand}",
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == item_count
    if expand:
        assert content["results"][0]["question"]["id"] == question.pk
        assert content["results"][0]["question"]["question"]["en"] == question.question
    else:
        assert content["results"][0]["question"] == question.pk


def test_answerviewset_list_expand_options_and_person(
    client, event, orga_read_token, choice_question, submission
):
    with scopes_disabled():
        option = choice_question.options.first()
        choice_answer = AnswerFactory(
            question=choice_question, submission=submission, answer=str(option.answer)
        )
        choice_answer.options.add(option)
        speaker = SpeakerFactory(event=event)
        speaker_question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
        )
        speaker_answer = AnswerFactory(
            question=speaker_question, submission=None, speaker=speaker, answer="42"
        )

    response = client.get(
        event.api_urls.answers + "?expand=options,person",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    results = {r["id"]: r for r in response.json()["results"]}
    assert set(results) == {choice_answer.pk, speaker_answer.pk}
    assert [o["id"] for o in results[choice_answer.pk]["options"]] == [option.pk]
    assert results[choice_answer.pk]["options"][0]["answer"] == {
        "en": str(option.answer)
    }
    assert results[choice_answer.pk]["person"] is None
    assert results[speaker_answer.pk]["person"]["code"] == speaker.code
    assert results[speaker_answer.pk]["options"] == []


def test_answerviewset_list_reviewer_returns_403(
    client, event, review_token, submission
):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
        is_visible_to_reviewers=True,
    )
    AnswerFactory(question=question, submission=submission, answer="42")

    response = client.get(
        event.api_urls.answers,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


def test_answerviewset_create_organiser(client, event, orga_write_token, submission):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
    )
    with scopes_disabled():
        count = Answer.objects.filter(question__event=event).count()
        initial_log_count = submission.logged_actions().count()

    response = client.post(
        event.api_urls.answers,
        data={
            "question": question.id,
            "submission": submission.code,
            "answer": "Tralalalala",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count + 1
        new_answer = Answer.objects.get(question=question, submission=submission)
        assert new_answer.answer == "Tralalalala"
        assert submission.logged_actions().count() == initial_log_count + 1
        log = submission.logged_actions().latest("timestamp")
        assert log.action_type == "pretalx.submission.update"
        assert log.data["changes"][f"question-{question.pk}"]["new"] == "Tralalalala"
    assert response.data == {
        "id": new_answer.pk,
        "question": question.pk,
        "answer": "Tralalalala",
        "answer_file": None,
        "submission": submission.code,
        "review": None,
        "person": None,
        "options": [],
    }


def test_answerviewset_edit_organiser(client, event, orga_write_token, submission):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
    )
    answer = AnswerFactory(question=question, submission=submission, answer="42")

    response = client.patch(
        event.api_urls.answers + f"{answer.pk}/",
        data={"answer": "ohno.png"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        answer.refresh_from_db()
        assert answer.answer == "ohno.png"


def test_answerviewset_update_rejects_option_count_over_limit(
    client, event, orga_write_token, submission
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.MULTIPLE,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            min_options=1,
            max_options=1,
        )
        first_option = AnswerOptionFactory(question=question)
        second_option = AnswerOptionFactory(question=question)
        answer = AnswerFactory(question=question, submission=submission)
        answer.options.set([first_option])

    response = client.patch(
        event.api_urls.answers + f"{answer.pk}/",
        data={"options": [first_option.pk, second_option.pk]},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    with scopes_disabled():
        assert list(answer.options.all()) == [first_option]


def test_answerviewset_create_required_fields(client, event, orga_write_token):
    response = client.post(
        event.api_urls.answers,
        data={},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.data.get("answer")[0] == "This field is required."
    assert response.data.get("question")[0] == "This field is required."


def test_answerviewset_create_duplicate_updates_existing(
    client, event, orga_write_token, submission
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        answer = AnswerFactory(question=question, submission=submission, answer="42")
        count = Answer.objects.filter(question__event=event).count()
        log_count_before = submission.logged_actions().count()
    headers = {"Authorization": f"Token {orga_write_token.token}"}
    data = {"question": question.pk, "submission": submission.code}

    response = client.post(
        event.api_urls.answers,
        data={**data, "answer": "Updated answer"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201, response.text
    assert response.data["id"] == answer.pk
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count
        answer.refresh_from_db()
        assert answer.answer == "Updated answer"
        assert submission.logged_actions().count() == log_count_before + 1
        log = submission.logged_actions().latest("timestamp")
        assert log.action_type == "pretalx.submission.update"
        assert log.data["changes"][f"question-{question.pk}"] == {
            "old": "42",
            "new": "Updated answer",
        }

    unchanged = client.post(
        event.api_urls.answers,
        data={**data, "answer": "Updated answer"},
        content_type="application/json",
        headers=headers,
    )

    assert unchanged.status_code == 201, unchanged.text
    with scopes_disabled():
        answer.refresh_from_db()
        assert answer.answer == "Updated answer"
        assert submission.logged_actions().count() == log_count_before + 1


def test_answerviewset_validation_submission_question_needs_submission(
    client, event, orga_write_token
):
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target="submission")

    response = client.post(
        event.api_urls.answers,
        data={"question": q.pk, "answer": "Test answer"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "submission": ["This field is required for submission questions."]
    }


@pytest.mark.parametrize(
    ("target", "right_input", "wrong_input"),
    (
        ("submission", "submission", "person"),
        ("submission", "submission", "review"),
        ("speaker", "person", "submission"),
        ("speaker", "person", "review"),
        ("reviewer", "review", "submission"),
        ("reviewer", "review", "person"),
    ),
)
def test_answerviewset_validation_rejects_other_target_inputs(
    client, event, orga_write_token, submission, target, right_input, wrong_input
):
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target=target)
        parent_values = {
            "submission": submission.code,
            "person": submission.speakers.first().code,
            "review": ReviewFactory(submission=submission).pk,
        }

    response = client.post(
        event.api_urls.answers,
        data={
            "question": q.pk,
            "answer": "Test answer",
            right_input: parent_values[right_input],
            wrong_input: parent_values[wrong_input],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.json() == {
        wrong_input: [f"Cannot set {wrong_input} for {target} question."]
    }


@pytest.mark.parametrize(
    ("variant", "selected"),
    ((QuestionVariant.CHOICES, 1), (QuestionVariant.MULTIPLE, 2)),
    ids=("choices", "multiple_choice"),
)
def test_answerviewset_create_choice_question(
    client, event, orga_write_token, submission, variant, selected
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=variant,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        options = [
            AnswerOptionFactory(question=question, answer=answer) for answer in "AB"
        ][:selected]

    response = client.post(
        event.api_urls.answers,
        data={
            "question": question.pk,
            "submission": submission.code,
            "answer": "ignored — value comes from options",
            "options": [option.pk for option in options],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        answer = Answer.objects.get(question=question, submission=submission)
        assert set(answer.options.all()) == set(options)
        assert answer.answer == ", ".join(str(option.answer) for option in options)


def test_answerviewset_create_file_question(
    client, event, orga_write_token, submission
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.FILE,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
    upload = SimpleUploadedFile(
        "answer.pdf", b"file content", content_type="application/pdf"
    )
    cached_file = CachedFileFactory(
        session_key=f"api-upload-{orga_write_token.token}",
        filename="answer.pdf",
        content_type="application/pdf",
        expires=timezone.now() + timezone.timedelta(hours=1),
    )
    cached_file.file.save("answer.pdf", upload)
    cached_file.save()

    response = client.post(
        event.api_urls.answers,
        data={
            "question": question.pk,
            "submission": submission.code,
            "answer": "answer.pdf",
            "answer_file": f"file:{cached_file.pk}",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        answer = Answer.objects.get(question=question, submission=submission)
        assert answer.answer.startswith("file://")
        assert answer.answer_file.name.startswith(f"{event.slug}/")

        cached_file.file.delete(save=False)

        with answer.answer_file.open("rb") as stored:
            assert stored.read() == b"file content"
