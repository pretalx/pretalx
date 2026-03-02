# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.api.versions import LEGACY
from pretalx.submission.icons import PLATFORM_ICONS
from pretalx.submission.models import Answer, AnswerOption, QuestionVariant
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_questionviewset_list_anonymous_sees_public_without_orga_fields(client, event):
    """Anonymous users see public questions without orga-only fields; non-public ones are hidden."""
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
        event.release_schedule("v1")

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
    """Organiser with a read token sees all questions regardless of visibility, with constant query count."""
    with scopes_disabled():
        questions = QuestionFactory.create_batch(
            item_count,
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )

    with django_assert_num_queries(15):
        response = client.get(
            event.api_urls.questions,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == item_count
    result_ids = {r["id"] for r in content["results"]}
    assert all(q.id in result_ids for q in questions)


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
    assert len(content["results"]) == 1
    assert content["results"][0]["id"] == visible_q.id


def test_questionviewset_create_organiser(client, event, orga_write_token):
    with scopes_disabled():
        count = event.questions(manager="all_objects").count()

    response = client.post(
        event.api_urls.questions,
        data={
            "question": "A question",
            "variant": "text",
            "target": "submission",
            "help_text": "hellllp",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert event.questions(manager="all_objects").count() == count + 1
        q = event.questions(manager="all_objects").first()
        assert q.question == "A question"
        assert q.variant == "text"
        assert q.target == "submission"
        assert q.help_text == "hellllp"
        assert q.logged_actions().filter(action_type="pretalx.question.create").exists()


def test_questionviewset_create_with_options(client, event, orga_write_token):
    response = client.post(
        event.api_urls.questions,
        data={
            "question": "A choice question",
            "variant": "choices",
            "target": "submission",
            "options": [{"answer": "Option 1"}, {"answer": "Option 2"}],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        q = event.questions(manager="all_objects").first()
        assert q.variant == "choices"
        assert q.options.count() == 2
        option_answers = [str(a) for a in q.options.values_list("answer", flat=True)]
        assert "Option 1" in option_answers
        assert "Option 2" in option_answers


def test_questionviewset_create_with_custom_identifier(client, event, orga_write_token):
    response = client.post(
        event.api_urls.questions,
        data={
            "question": "A question with identifier",
            "variant": "text",
            "target": "submission",
            "identifier": "MY-CUSTOM-ID",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["identifier"] == "MY-CUSTOM-ID"


def test_questionviewset_create_without_identifier_auto_generates(
    client, event, orga_write_token
):
    response = client.post(
        event.api_urls.questions,
        data={
            "question": "A question without identifier",
            "variant": "text",
            "target": "submission",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    identifier = response.json()["identifier"]
    assert identifier is not None
    assert len(identifier) == 8


def test_questionviewset_create_read_only_token_returns_403(
    client, event, orga_read_token
):
    with scopes_disabled():
        count = event.questions(manager="all_objects").count()

    response = client.post(
        event.api_urls.questions,
        data={"question": "A question", "variant": "text", "target": "submission"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert event.questions(manager="all_objects").count() == count


def test_questionviewset_create_other_event_returns_403(client, orga_read_token):
    other_event = EventFactory()
    with scopes_disabled():
        count = other_event.questions(manager="all_objects").count()

    response = client.post(
        other_event.api_urls.questions,
        data={"question": "A question", "variant": "text", "target": "submission"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert other_event.questions(manager="all_objects").count() == count


def test_questionviewset_edit_organiser(client, event, orga_write_token):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )

    response = client.patch(
        event.api_urls.questions + f"{question.pk}/",
        data={"target": "speaker", "help_text": "hellllp"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        question.refresh_from_db()
        assert question.target == "speaker"
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
        choice_question.refresh_from_db()
        assert choice_question.options.count() == 2
        new_options = [o.answer for o in choice_question.options.all()]
        assert "Updated Option 1" in new_options
        assert "Original Option 1" not in new_options


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


def test_questionviewset_filter_by_target(client, event, orga_read_token):
    with scopes_disabled():
        QuestionFactory(event=event, variant="text", target="submission")
        QuestionFactory(event=event, variant="text", target="speaker")

    response = client.get(
        event.api_urls.questions + "?target=speaker",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["target"] == "speaker"


def test_questionviewset_filter_by_variant(client, event, orga_read_token):
    with scopes_disabled():
        QuestionFactory(event=event, variant="text", target="submission")
        QuestionFactory(event=event, variant="boolean", target="submission")

    response = client.get(
        event.api_urls.questions + "?variant=boolean",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["variant"] == "boolean"


def test_questionviewset_search(client, event, orga_read_token):
    with scopes_disabled():
        QuestionFactory(
            event=event,
            question="Special question",
            variant="text",
            target="submission",
        )
        QuestionFactory(
            event=event,
            question="Regular question",
            variant="text",
            target="submission",
        )

    response = client.get(
        event.api_urls.questions + "?q=special",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["question"]["en"] == "Special question"


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


def test_questionviewset_create_legacy_version_returns_400(
    client, event, orga_write_token
):
    response = client.post(
        event.api_urls.questions,
        data={"question": "A question", "variant": "text", "target": "submission"},
        content_type="application/json",
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )

    assert response.status_code == 400, response.text
    assert "API version not supported." in response.text


def test_questionviewset_icon_returns_svg(client, event, orga_read_token):
    with scopes_disabled():
        icon_name = next(iter(PLATFORM_ICONS))
        q = QuestionFactory(
            event=event,
            variant=QuestionVariant.URL,
            target="submission",
            icon=icon_name,
        )

    response = client.get(
        event.api_urls.questions + f"{q.pk}/icon/",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert "<svg" in response.content.decode()


def test_questionviewset_icon_returns_404_without_icon(client, event, orga_read_token):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )

    response = client.get(
        event.api_urls.questions + f"{question.pk}/icon/",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 404


def test_answeroptionviewset_list_organiser(
    client, event, orga_read_token, choice_question
):
    with scopes_disabled():
        option_count = choice_question.options.count()
        assert option_count > 0

    response = client.get(
        event.api_urls.question_options,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200, response.text
    content = response.json()
    assert content["count"] == option_count


def test_answeroptionviewset_filter_by_question(
    client, event, orga_read_token, choice_question
):
    with scopes_disabled():
        other_q = QuestionFactory(
            event=event, variant=QuestionVariant.CHOICES, target="submission"
        )
        AnswerOptionFactory(question=other_q)
        option_count = choice_question.options.count()

    response = client.get(
        event.api_urls.question_options + f"?question={choice_question.pk}",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200, response.text
    content = response.json()
    assert content["count"] == option_count
    assert all(opt["question"] == choice_question.pk for opt in content["results"])


def test_answeroptionviewset_retrieve(client, event, orga_read_token, choice_question):
    with scopes_disabled():
        option = choice_question.options.first()

    response = client.get(
        event.api_urls.question_options + f"{option.pk}/",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200, response.text
    content = response.json()
    assert content["id"] == option.pk
    assert content["answer"]["en"] == option.answer


def test_answeroptionviewset_create(client, event, orga_write_token, choice_question):
    with scopes_disabled():
        initial_count = choice_question.options.count()

    response = client.post(
        event.api_urls.question_options,
        data={
            "question": choice_question.pk,
            "answer": {"en": "New API Option"},
            "position": initial_count + 1,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    content = response.json()
    assert content["answer"]["en"] == "New API Option"
    assert content["question"] == choice_question.pk
    with scopes_disabled():
        assert choice_question.options.count() == initial_count + 1


def test_answeroptionviewset_create_with_identifier(
    client, event, orga_write_token, choice_question
):
    response = client.post(
        event.api_urls.question_options,
        data={
            "question": choice_question.pk,
            "answer": {"en": "Option with ID"},
            "identifier": "OPT-CUSTOM",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["identifier"] == "OPT-CUSTOM"


def test_answeroptionviewset_create_wrong_question_type_returns_400(
    client, event, orga_write_token
):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
    )

    response = client.post(
        event.api_urls.question_options,
        data={"question": question.pk, "answer": {"en": "Invalid Option"}},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert "question" in response.data
    assert "Invalid pk" in str(response.data["question"])


def test_answeroptionviewset_update(client, event, orga_write_token, choice_question):
    with scopes_disabled():
        option = choice_question.options.first()

    response = client.patch(
        event.api_urls.question_options + f"{option.pk}/",
        data={"answer": {"en": "Updated via API"}},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["answer"]["en"] == "Updated via API"
    with scopes_disabled():
        option.refresh_from_db()
        assert str(option.answer) == "Updated via API"


def test_answeroptionviewset_delete(client, event, orga_write_token, choice_question):
    with scopes_disabled():
        option = choice_question.options.last()
        option_id = option.pk
        initial_count = choice_question.options.count()

    response = client.delete(
        event.api_urls.question_options + f"{option_id}/",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204, response.text
    with scopes_disabled():
        assert choice_question.options.count() == initial_count - 1
        assert not choice_question.options.filter(pk=option_id).exists()


def test_answeroptionviewset_reviewer_sees_visible_options(client, event, review_token):
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.CHOICES,
        target="speaker",
        is_visible_to_reviewers=True,
    )
    AnswerOptionFactory(question=question)

    response = client.get(
        event.api_urls.question_options,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert len(content["results"]) == 1


def test_answeroptionviewset_anonymous_nonpublic_question_empty(client, event):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.CHOICES,
            target="speaker",
            is_public=False,
        )
        AnswerOptionFactory(question=question)
        event.release_schedule("v1")

    response = client.get(event.api_urls.question_options)

    assert response.status_code == 200, response.text
    assert response.json()["count"] == 0


def test_answeroptionviewset_anonymous_public_question(client, event):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.CHOICES,
            target="speaker",
            is_public=True,
        )
        AnswerOptionFactory.create_batch(3, question=question)
        event.release_schedule("v1")

    response = client.get(event.api_urls.question_options)

    assert response.status_code == 200, response.text
    assert response.json()["count"] == 3


def test_answeroptionviewset_expand_question(
    client, event, orga_read_token, choice_question
):
    with scopes_disabled():
        track = TrackFactory(event=event)
        choice_question.tracks.add(track)

    response = client.get(
        event.api_urls.question_options + "?expand=question",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200, response.text
    content = response.json()
    assert isinstance(content["results"][0]["question"], dict)
    assert content["results"][0]["question"]["id"] == choice_question.pk


def test_answeroptionviewset_expand_question_tracks(
    client, event, orga_read_token, choice_question
):
    with scopes_disabled():
        track = TrackFactory(event=event)
        choice_question.tracks.add(track)

    response = client.get(
        event.api_urls.question_options + "?expand=question,question.tracks",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200, response.text
    content = response.json()
    question_data = content["results"][0]["question"]
    assert isinstance(question_data["tracks"], list)
    assert len(question_data["tracks"]) == 1
    assert question_data["tracks"][0]["name"]["en"] == track.name


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
def test_answerviewset_list_organiser(
    client, event, orga_read_token, submission, django_assert_num_queries, item_count
):
    """Organiser can list answers; query count is constant."""
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

    with django_assert_num_queries(13):
        response = client.get(
            event.api_urls.answers,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == item_count


def test_answerviewset_list_expand_options(
    client, event, orga_read_token, choice_question, submission
):
    with scopes_disabled():
        option = choice_question.options.first()
        answer = AnswerFactory(
            question=choice_question, submission=submission, answer=str(option.answer)
        )
        answer.options.add(option)

    response = client.get(
        event.api_urls.answers + "?expand=options",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) >= 1
    answer_data = next(r for r in content["results"] if r["id"] == answer.pk)
    assert answer_data["options"][0]["id"] == option.pk
    assert "answer" in answer_data["options"][0]


def test_answerviewset_list_reviewer_returns_403(
    client, event, review_token, submission
):
    """Reviewers cannot list answers (requires submission.api_answer permission)."""
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
        speaker_profile = submission.speakers.first()
        count = Answer.objects.filter(question__event=event).count()

    response = client.post(
        event.api_urls.answers,
        data={
            "question": question.id,
            "submission": submission.code,
            "person": speaker_profile.code,
            "answer": "Tralalalala",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count + 1
        new_answer = Answer.objects.filter(question__event=event).first()
        assert new_answer.answer == "Tralalalala"


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

    response = client.post(
        event.api_urls.answers,
        data={
            "question": answer.question_id,
            "submission": answer.submission.code,
            "answer": "Updated answer",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count
        answer.refresh_from_db()
        assert answer.answer == "Updated answer"


def test_answerviewset_create_duplicate_same_value_skips_log(
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
        log_count_before = answer.submission.logged_actions().count()

    response = client.post(
        event.api_urls.answers,
        data={
            "question": answer.question_id,
            "submission": answer.submission.code,
            "answer": answer.answer,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        answer.refresh_from_db()
        assert answer.answer == "42"
        log_count_after = answer.submission.logged_actions().count()
        assert log_count_after == log_count_before


def test_answeroptionviewset_delete_used_option_returns_400(
    client, event, orga_write_token, choice_question
):
    with scopes_disabled():
        option = choice_question.options.first()
        answer = AnswerFactory(question=choice_question, answer=str(option.answer))
        answer.options.add(option)

    response = client.delete(
        event.api_urls.question_options + f"{option.pk}/",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    with scopes_disabled():
        assert AnswerOption.objects.filter(pk=option.pk).exists()


def test_answerviewset_create_logs_to_submission(
    client, event, orga_write_token, submission
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        initial_log_count = submission.logged_actions().count()

    response = client.post(
        event.api_urls.answers,
        data={
            "question": question.pk,
            "submission": submission.code,
            "answer": "Test answer",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert submission.logged_actions().count() == initial_log_count + 1
        log = submission.logged_actions().latest("timestamp")
        assert log.action_type == "pretalx.submission.update"
        assert "changes" in log.data
        assert log.data["changes"][f"question-{question.pk}"]["new"] == "Test answer"


def test_answerviewset_update_logs_change(client, event, orga_write_token, submission):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
        )
        answer = AnswerFactory(question=question, submission=submission, answer="42")
        old_answer = answer.answer

    response = client.post(
        event.api_urls.answers,
        data={
            "question": answer.question_id,
            "submission": answer.submission.code,
            "answer": "Updated answer",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        log = answer.submission.logged_actions().latest("timestamp")
        assert log.action_type == "pretalx.submission.update"
        key = f"question-{answer.question_id}"
        assert log.data["changes"][key]["old"] == old_answer
        assert log.data["changes"][key]["new"] == "Updated answer"


def test_answerviewset_validation_submission_question_needs_submission(
    client, event, orga_write_token, submission
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
    assert "submission" in response.data

    response = client.post(
        event.api_urls.answers,
        data={
            "question": q.pk,
            "answer": "Test answer",
            "submission": submission.code,
            "review": 1,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "review" in response.data
