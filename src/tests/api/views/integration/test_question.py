import json

import pytest
from django_scopes import scopes_disabled

from pretalx.api.versions import LEGACY
from pretalx.submission.icons import PLATFORM_ICONS
from pretalx.submission.models import Answer, AnswerOption, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    QuestionFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize("is_public", (True, False))
def test_questionviewset_list_anonymous_sees_only_public(client, question, is_public):
    """Anonymous users only see public questions; non-public ones are hidden."""
    with scopes_disabled():
        question.is_public = is_public
        question.save()
        question.event.is_public = True
        question.event.save()
        # Release a schedule so the anonymous user has list_question permission
        question.event.release_schedule("v1")

    response = client.get(question.event.api_urls.questions, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert bool(len(content["results"])) is is_public


@pytest.mark.django_db
def test_questionviewset_list_anonymous_private_event_returns_401(client, event):
    """Anonymous users get 401 on a private event."""
    event.is_public = False
    event.save()

    response = client.get(event.api_urls.questions, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_questionviewset_list_public_questions_lack_orga_fields(client, question):
    """Public questions served to anonymous users do not contain orga-only fields."""
    with scopes_disabled():
        question.is_public = True
        question.save()
        question.event.is_public = True
        question.event.save()
        question.event.release_schedule("v1")

    response = client.get(question.event.api_urls.questions, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["results"][0]["question"]["en"] == question.question
    assert "is_visible_to_reviewers" not in content["results"][0]
    assert "contains_personal_data" not in content["results"][0]


@pytest.mark.django_db
def test_questionviewset_list_organiser_sees_all(client, orga_read_token, question):
    """Organiser with a read token sees all questions regardless of visibility."""
    response = client.get(
        question.event.api_urls.questions,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1
    assert content["results"][0]["id"] == question.id


@pytest.mark.django_db
@pytest.mark.parametrize("is_visible", (True, False))
def test_questionviewset_list_reviewer_visibility(
    client, review_token, question, is_visible
):
    """Reviewers only see questions marked visible to reviewers."""
    with scopes_disabled():
        question.is_visible_to_reviewers = is_visible
        question.save()

    response = client.get(
        question.event.api_urls.questions,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert bool(len(content["results"])) is is_visible


@pytest.mark.django_db
def test_questionviewset_create_organiser(client, event, orga_write_token):
    """Organiser with a write token can create a question."""
    with scopes_disabled():
        count = event.questions(manager="all_objects").count()

    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {
                "question": "A question",
                "variant": "text",
                "target": "submission",
                "help_text": "hellllp",
            }
        ),
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


@pytest.mark.django_db
def test_questionviewset_create_with_options(client, event, orga_write_token):
    """Organiser can create a choice question with inline options."""
    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {
                "question": "A choice question",
                "variant": "choices",
                "target": "submission",
                "options": [{"answer": "Option 1"}, {"answer": "Option 2"}],
            }
        ),
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


@pytest.mark.django_db
def test_questionviewset_create_with_custom_identifier(client, event, orga_write_token):
    """Organiser can create a question with a custom identifier."""
    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {
                "question": "A question with identifier",
                "variant": "text",
                "target": "submission",
                "identifier": "MY-CUSTOM-ID",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["identifier"] == "MY-CUSTOM-ID"


@pytest.mark.django_db
def test_questionviewset_create_without_identifier_auto_generates(
    client, event, orga_write_token
):
    """Question without explicit identifier gets an auto-generated 8-char one."""
    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {
                "question": "A question without identifier",
                "variant": "text",
                "target": "submission",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    identifier = response.json()["identifier"]
    assert identifier is not None
    assert len(identifier) == 8


@pytest.mark.django_db
def test_questionviewset_create_read_only_token_returns_403(
    client, event, orga_read_token
):
    """Organiser with a read-only token cannot create questions."""
    with scopes_disabled():
        count = event.questions(manager="all_objects").count()

    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {"question": "A question", "variant": "text", "target": "submission"}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert event.questions(manager="all_objects").count() == count


@pytest.mark.django_db
def test_questionviewset_create_reviewer_returns_403(client, event, review_token):
    """Reviewers cannot create questions."""
    with scopes_disabled():
        count = event.questions(manager="all_objects").count()

    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {"question": "A question", "variant": "text", "target": "submission"}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert event.questions(manager="all_objects").count() == count


@pytest.mark.django_db
def test_questionviewset_create_other_event_returns_403(
    client, other_event, orga_read_token
):
    """Organiser cannot create questions on an event they don't have access to."""
    with scopes_disabled():
        count = other_event.questions(manager="all_objects").count()

    response = client.post(
        other_event.api_urls.questions,
        data=json.dumps(
            {"question": "A question", "variant": "text", "target": "submission"}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert other_event.questions(manager="all_objects").count() == count


@pytest.mark.django_db
def test_questionviewset_edit_organiser(client, event, orga_write_token, question):
    """Organiser with write token can edit a question."""
    response = client.patch(
        event.api_urls.questions + f"{question.pk}/",
        data=json.dumps({"target": "speaker", "help_text": "hellllp"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        question.refresh_from_db()
        assert question.target == "speaker"
        assert question.help_text == "hellllp"


@pytest.mark.django_db
def test_questionviewset_edit_reviewer_returns_403(
    client, event, review_token, question
):
    """Reviewers cannot edit questions."""
    response = client.patch(
        event.api_urls.questions + f"{question.pk}/",
        data=json.dumps({"target": "speaker", "help_text": "hellllp"}),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        question.refresh_from_db()
        assert question.target != "speaker"
        assert question.help_text != "hellllp"


@pytest.mark.django_db
def test_questionviewset_edit_options(client, event, orga_write_token, choice_question):
    """Editing question options replaces existing options entirely."""
    with scopes_disabled():
        assert choice_question.options.count() == 3

    response = client.patch(
        event.api_urls.questions + f"{choice_question.pk}/",
        data=json.dumps(
            {"options": [{"answer": "Updated Option 1"}, {"answer": "New Option"}]}
        ),
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


@pytest.mark.django_db
def test_questionviewset_delete_organiser(client, event, orga_write_token):
    """Organiser with write token can delete a question without answers."""
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


@pytest.mark.django_db
def test_questionviewset_delete_read_only_token_returns_403(
    client, event, orga_read_token
):
    """Organiser with read-only token cannot delete questions."""
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target="submission")
        pk = q.pk

    response = client.delete(
        event.api_urls.questions + f"{pk}/",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert event.questions(manager="all_objects").filter(pk=pk).exists()


@pytest.mark.django_db
def test_questionviewset_delete_with_answers_returns_400(
    client, event, orga_write_token, answer
):
    """Questions with answers cannot be deleted — returns 400."""
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


@pytest.mark.django_db
def test_questionviewset_filter_by_target(client, event, orga_read_token):
    """?target=speaker filters to only speaker-targeted questions."""
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


@pytest.mark.django_db
def test_questionviewset_filter_by_variant(client, event, orga_read_token):
    """?variant=boolean filters to only boolean-variant questions."""
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


@pytest.mark.django_db
def test_questionviewset_search(client, event, orga_read_token):
    """?q= searches question text."""
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


@pytest.mark.django_db
def test_questionviewset_expand_options_tracks_submission_types(
    client, event, orga_read_token, choice_question
):
    """?expand= inlines related options, tracks, and submission_types."""
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


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_questionviewset_list_query_count(
    client, event, orga_read_token, django_assert_num_queries, item_count
):
    """Query count is constant regardless of the number of questions."""
    with scopes_disabled():
        for _i in range(item_count):
            QuestionFactory(event=event, variant="text", target="speaker")

    with django_assert_num_queries(15):
        response = client.get(
            event.api_urls.questions,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200, response.text
    content = response.json()
    assert content["count"] == item_count


@pytest.mark.django_db
@pytest.mark.parametrize(("is_detail", "method"), ((False, "post"), (True, "put")))
def test_questionviewset_question_field_required(
    client, event, orga_write_token, question, is_detail, method
):
    """The 'question' field is required on create and full update."""
    url = event.api_urls.questions
    if is_detail:
        url += f"{question.pk}/"

    response = getattr(client, method)(
        url,
        data=json.dumps({}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.data.get("question")[0] == "This field is required."


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_detail", "method"), ((False, "post"), (True, "put"), (True, "patch"))
)
def test_questionviewset_question_required_valid_choice(
    client, event, orga_write_token, question, is_detail, method
):
    """question_required must be a valid choice value."""
    url = event.api_urls.questions
    if is_detail:
        url += f"{question.pk}/"

    response = getattr(client, method)(
        url,
        data=json.dumps({"question_required": "invalid_choice"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert (
        response.data.get("question_required")[0]
        == '"invalid_choice" is not a valid choice.'
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_detail", "method"), ((False, "post"), (True, "put"), (True, "patch"))
)
def test_questionviewset_contains_personal_data_valid_boolean(
    client, event, orga_write_token, question, is_detail, method
):
    """contains_personal_data must be a valid boolean."""
    url = event.api_urls.questions
    if is_detail:
        url += f"{question.pk}/"

    response = getattr(client, method)(
        url,
        data=json.dumps({"contains_personal_data": "not_a_boolean"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.data.get("contains_personal_data")[0] == "Must be a valid boolean."


@pytest.mark.django_db
def test_questionviewset_create_with_track_from_other_event_returns_400(
    client, event, orga_write_token, other_event
):
    """Cannot create a question with a track from a different event."""
    with scopes_disabled():
        other_track = TrackFactory(event=other_event)

    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {
                "question": "Question with invalid track",
                "variant": "text",
                "target": "submission",
                "tracks": [other_track.pk],
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert "tracks" in response.data
    with scopes_disabled():
        assert not event.questions(manager="all_objects").exists()


@pytest.mark.django_db
def test_questionviewset_create_legacy_version_returns_400(
    client, event, orga_write_token
):
    """Creating questions via the legacy API version returns 400."""
    response = client.post(
        event.api_urls.questions,
        data=json.dumps(
            {"question": "A question", "variant": "text", "target": "submission"}
        ),
        content_type="application/json",
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )

    assert response.status_code == 400, response.text
    assert "API version not supported." in response.text


@pytest.mark.django_db
def test_questionviewset_icon_returns_svg(client, event, orga_read_token):
    """The icon endpoint returns an SVG when the question has a valid icon."""
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


@pytest.mark.django_db
def test_questionviewset_icon_returns_404_without_icon(
    client, event, orga_read_token, question
):
    """The icon endpoint returns 404 when the question has no icon."""
    response = client.get(
        event.api_urls.questions + f"{question.pk}/icon/",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_answeroptionviewset_list_organiser(
    client, event, orga_read_token, choice_question
):
    """Organiser can list answer options."""
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


@pytest.mark.django_db
def test_answeroptionviewset_filter_by_question(
    client, event, orga_read_token, choice_question
):
    """?question= filters options to a single question."""
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


@pytest.mark.django_db
def test_answeroptionviewset_retrieve(client, event, orga_read_token, choice_question):
    """Organiser can retrieve a single answer option."""
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


@pytest.mark.django_db
def test_answeroptionviewset_create(client, event, orga_write_token, choice_question):
    """Organiser with write token can create an answer option."""
    with scopes_disabled():
        initial_count = choice_question.options.count()

    response = client.post(
        event.api_urls.question_options,
        data=json.dumps(
            {
                "question": choice_question.pk,
                "answer": {"en": "New API Option"},
                "position": initial_count + 1,
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    content = response.json()
    assert content["answer"]["en"] == "New API Option"
    assert content["question"] == choice_question.pk
    with scopes_disabled():
        assert choice_question.options.count() == initial_count + 1


@pytest.mark.django_db
def test_answeroptionviewset_create_with_identifier(
    client, event, orga_write_token, choice_question
):
    """Options can be created with a custom identifier."""
    response = client.post(
        event.api_urls.question_options,
        data=json.dumps(
            {
                "question": choice_question.pk,
                "answer": {"en": "Option with ID"},
                "identifier": "OPT-CUSTOM",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["identifier"] == "OPT-CUSTOM"


@pytest.mark.django_db
def test_answeroptionviewset_create_wrong_question_type_returns_400(
    client, event, orga_write_token, question
):
    """Cannot create options for non-choice questions (e.g. number)."""
    response = client.post(
        event.api_urls.question_options,
        data=json.dumps({"question": question.pk, "answer": {"en": "Invalid Option"}}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert "question" in response.data
    assert "Invalid pk" in str(response.data["question"])


@pytest.mark.django_db
def test_answeroptionviewset_update(client, event, orga_write_token, choice_question):
    """Organiser can update an answer option."""
    with scopes_disabled():
        option = choice_question.options.first()

    response = client.patch(
        event.api_urls.question_options + f"{option.pk}/",
        data=json.dumps({"answer": {"en": "Updated via API"}}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["answer"]["en"] == "Updated via API"
    with scopes_disabled():
        option.refresh_from_db()
        assert str(option.answer) == "Updated via API"


@pytest.mark.django_db
def test_answeroptionviewset_delete(client, event, orga_write_token, choice_question):
    """Organiser can delete an unused answer option."""
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


@pytest.mark.django_db
@pytest.mark.parametrize("is_visible", (True, False))
def test_answeroptionviewset_reviewer_visibility(
    client, event, review_token, choice_question, is_visible
):
    """Reviewer access to options depends on question's is_visible_to_reviewers."""
    with scopes_disabled():
        choice_question.is_visible_to_reviewers = is_visible
        choice_question.save()

    response = client.get(
        event.api_urls.question_options,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert bool(len(content["results"])) is is_visible


@pytest.mark.django_db
def test_answeroptionviewset_anonymous_private_event_returns_401(
    client, event, choice_question
):
    """Anonymous users get 401 on a private event."""
    event.is_public = False
    event.save()

    response = client.get(event.api_urls.question_options)

    assert response.status_code == 401


@pytest.mark.django_db
def test_answeroptionviewset_anonymous_nonpublic_question_empty(
    client, event, choice_question
):
    """Anonymous users see no options for non-public questions."""
    with scopes_disabled():
        choice_question.is_public = False
        choice_question.save()
        event.is_public = True
        event.save()
        event.release_schedule("v1")

    response = client.get(event.api_urls.question_options)

    assert response.status_code == 200, response.text
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_answeroptionviewset_anonymous_public_question(client, event, choice_question):
    """Anonymous users can see options for public questions."""
    with scopes_disabled():
        choice_question.is_public = True
        choice_question.save()
        count = choice_question.options.count()
        event.is_public = True
        event.save()
        event.release_schedule("v1")

    response = client.get(event.api_urls.question_options)

    assert response.status_code == 200, response.text
    assert response.json()["count"] == count


@pytest.mark.django_db
def test_answeroptionviewset_expand_question(
    client, event, orga_read_token, choice_question
):
    """?expand=question inlines the full question object."""
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


@pytest.mark.django_db
def test_answeroptionviewset_expand_question_tracks(
    client, event, orga_read_token, choice_question
):
    """?expand=question,question.tracks inlines question with expanded tracks."""
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


@pytest.mark.django_db
def test_answerviewset_list_anonymous_returns_401(client, event, answer):
    """Anonymous users cannot access answers."""
    response = client.get(event.api_urls.answers, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_answerviewset_list_organiser(
    client, orga_read_token, answer, django_assert_num_queries, item_count
):
    """Organiser can list answers; query count is constant."""
    for _ in range(1, item_count):
        with scopes_disabled():
            AnswerFactory(
                question=answer.question,
                submission=answer.submission,
                answer="second answer",
            )

    with django_assert_num_queries(13):
        response = client.get(
            answer.event.api_urls.answers,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == item_count


@pytest.mark.django_db
def test_answerviewset_list_expand_options(
    client, event, orga_read_token, choice_question, submission
):
    """Expanding options on answers inlines the option objects."""
    with scopes_disabled():
        option = choice_question.options.first()
        answer = Answer.objects.create(
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


@pytest.mark.django_db
@pytest.mark.parametrize("is_visible", (True, False))
def test_answerviewset_list_reviewer_returns_403(
    client, review_token, answer, is_visible
):
    """Reviewers cannot list answers (requires submission.api_answer permission)."""
    with scopes_disabled():
        answer.question.is_visible_to_reviewers = is_visible
        answer.question.save()

    response = client.get(
        answer.event.api_urls.answers,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_answerviewset_create_organiser(
    client, event, orga_write_token, question, submission, speaker_profile
):
    """Organiser with write token can create an answer."""
    with scopes_disabled():
        count = Answer.objects.filter(question__event=event).count()

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": question.id,
                "submission": submission.code,
                "person": speaker_profile.code,
                "answer": "Tralalalala",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count + 1
        new_answer = Answer.objects.filter(question__event=event).first()
        assert new_answer.answer == "Tralalalala"


@pytest.mark.django_db
def test_answerviewset_create_reviewer_returns_403(
    client, event, review_token, question, submission, speaker_profile
):
    """Reviewers cannot create answers."""
    with scopes_disabled():
        count = Answer.objects.filter(question__event=event).count()

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": question.id,
                "submission": submission.code,
                "person": speaker_profile.code,
                "answer": "Tralalalala",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count


@pytest.mark.django_db
def test_answerviewset_edit_organiser(client, event, orga_write_token, answer):
    """Organiser can edit an answer."""
    response = client.patch(
        event.api_urls.answers + f"{answer.pk}/",
        data=json.dumps({"answer": "ohno.png"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        answer.refresh_from_db()
        assert answer.answer == "ohno.png"


@pytest.mark.django_db
def test_answerviewset_edit_reviewer_returns_403(client, event, review_token, answer):
    """Reviewers cannot edit answers."""
    response = client.patch(
        event.api_urls.answers + f"{answer.pk}/",
        data=json.dumps({"answer": "ohno.png"}),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        answer.refresh_from_db()
        assert answer.answer != "ohno.png"


@pytest.mark.django_db
@pytest.mark.parametrize("required_field", ("answer", "question"))
def test_answerviewset_create_required_fields(
    client, event, orga_write_token, required_field
):
    """Both 'answer' and 'question' are required on answer creation."""
    response = client.post(
        event.api_urls.answers,
        data=json.dumps({}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.data.get(required_field)[0] == "This field is required."


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_detail", "method"), ((False, "post"), (True, "put"), (True, "patch"))
)
def test_answerviewset_blank_answer_returns_400(
    client, event, orga_write_token, answer, is_detail, method
):
    """Blank answer values are rejected."""
    url = event.api_urls.answers
    if is_detail:
        url += f"{answer.pk}/"

    response = getattr(client, method)(
        url,
        data=json.dumps({"answer": ""}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.data.get("answer")[0] == "This field may not be blank."


@pytest.mark.django_db
def test_answerviewset_create_duplicate_updates_existing(
    client, event, orga_write_token, answer
):
    """Creating an answer for the same question+submission updates the existing one."""
    with scopes_disabled():
        count = Answer.objects.filter(question__event=event).count()

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": answer.question_id,
                "submission": answer.submission.code,
                "answer": "Updated answer",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert Answer.objects.filter(question__event=event).count() == count
        answer.refresh_from_db()
        assert answer.answer == "Updated answer"


@pytest.mark.django_db
def test_answerviewset_create_duplicate_same_value_skips_log(
    client, event, orga_write_token, answer
):
    """Creating a duplicate answer with the same value does not log an update."""
    with scopes_disabled():
        log_count_before = answer.submission.logged_actions().count()

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": answer.question_id,
                "submission": answer.submission.code,
                "answer": answer.answer,
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        answer.refresh_from_db()
        assert answer.answer == "42"
        log_count_after = answer.submission.logged_actions().count()
        assert log_count_after == log_count_before


@pytest.mark.django_db
def test_answeroptionviewset_delete_used_option_returns_400(
    client, event, orga_write_token, choice_question
):
    """Deleting an answer option that has answers returns 400 (ProtectedError)."""
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


@pytest.mark.django_db
def test_answerviewset_create_logs_to_submission(
    client, event, orga_write_token, submission, question
):
    """Creating an answer logs the change to the parent submission."""
    with scopes_disabled():
        initial_log_count = submission.logged_actions().count()

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": question.pk,
                "submission": submission.code,
                "answer": "Test answer",
            }
        ),
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


@pytest.mark.django_db
def test_answerviewset_update_logs_change(client, event, orga_write_token, answer):
    """Updating an answer via create logs both old and new values."""
    with scopes_disabled():
        old_answer = answer.answer

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": answer.question_id,
                "submission": answer.submission.code,
                "answer": "Updated answer",
            }
        ),
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


@pytest.mark.django_db
def test_answerviewset_validation_submission_question_needs_submission(
    client, event, orga_write_token, submission
):
    """Submission-targeted question requires a submission and rejects review."""
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target="submission")

    response = client.post(
        event.api_urls.answers,
        data=json.dumps({"question": q.pk, "answer": "Test answer"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "submission" in response.data

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": q.pk,
                "answer": "Test answer",
                "submission": submission.code,
                "review": 1,
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "review" in response.data


@pytest.mark.django_db
def test_answerviewset_validation_reviewer_question_needs_review(
    client, event, orga_write_token, review
):
    """Reviewer-targeted question requires a review and rejects submission."""
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target="reviewer")

    response = client.post(
        event.api_urls.answers,
        data=json.dumps({"question": q.pk, "answer": "Test answer"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "review" in response.data

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": q.pk,
                "answer": "Test answer",
                "review": review.pk,
                "submission": "abc123",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "submission" in response.data


@pytest.mark.django_db
def test_answerviewset_validation_speaker_question_needs_person(
    client, event, orga_write_token, speaker_profile
):
    """Speaker-targeted question requires a person and rejects submission."""
    with scopes_disabled():
        q = QuestionFactory(event=event, variant="text", target="speaker")

    response = client.post(
        event.api_urls.answers,
        data=json.dumps({"question": q.pk, "answer": "Test answer"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "person" in response.data

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": q.pk,
                "answer": "Test answer",
                "person": speaker_profile.code,
                "submission": "abc123",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "submission" in response.data


@pytest.mark.parametrize("target", ("submission", "reviewer", "speaker"))
@pytest.mark.django_db
def test_answerviewset_create_superfluous_fields_returns_400(
    client,
    event,
    orga_write_token,
    question,
    submission,
    speaker_profile,
    review,
    target,
):
    """Providing all three related fields (submission, person, review) is always rejected."""
    with scopes_disabled():
        question.target = target
        question.save()

    response = client.post(
        event.api_urls.answers,
        data=json.dumps(
            {
                "question": question.id,
                "submission": submission.code,
                "person": speaker_profile.code,
                "review": review.pk,
                "answer": "Tralalalala",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400, response.text
