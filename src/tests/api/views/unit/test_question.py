# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.api.serializers.question import (
    AnswerOptionCreateSerializer,
    AnswerOptionSerializer,
    QuestionOrgaSerializer,
)
from pretalx.api.views.question import AnswerOptionViewSet, QuestionViewSet
from pretalx.submission.models import QuestionTarget, QuestionVariant
from tests.factories import AnswerOptionFactory, EventFactory, QuestionFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_question_viewset_get_queryset_orga_sees_all_event_questions():
    question_active = QuestionFactory(active=True)
    event = question_active.event
    question_inactive = QuestionFactory(event=event, active=False)
    question_reviewer = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True
    )
    QuestionFactory(active=True)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_api_request(event=event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    assert set(view.get_queryset()) == {
        question_active,
        question_inactive,
        question_reviewer,
    }


@pytest.mark.parametrize(
    ("action", "expected"),
    (("create", AnswerOptionCreateSerializer), ("list", AnswerOptionSerializer)),
)
def test_answeroption_viewset_get_unversioned_serializer_class(action, expected):
    view = make_view(AnswerOptionViewSet, make_api_request())
    view.action = action

    assert view.get_unversioned_serializer_class() is expected


def test_answeroption_viewset_get_queryset_returns_visible_choice_options():
    event = EventFactory(is_public=False)
    choice_question = QuestionFactory(
        event=event, variant=QuestionVariant.CHOICES, active=True, is_public=True
    )
    multiple_question = QuestionFactory(event=event, variant=QuestionVariant.MULTIPLE)
    number_question = QuestionFactory(event=event, variant=QuestionVariant.NUMBER)
    string_question = QuestionFactory(event=event, variant=QuestionVariant.STRING)
    choice_option = AnswerOptionFactory(question=choice_question)
    multiple_option = AnswerOptionFactory(question=multiple_question)
    AnswerOptionFactory(question=number_question)
    AnswerOptionFactory(question=string_question)
    AnswerOptionFactory(question__variant=QuestionVariant.CHOICES)
    user = make_orga_user(event, can_change_event_settings=True)

    orga_view = make_view(AnswerOptionViewSet, make_api_request(event=event, user=user))
    anonymous_view = make_view(AnswerOptionViewSet, make_api_request(event=event))

    assert set(orga_view.get_queryset()) == {choice_option, multiple_option}
    assert list(anonymous_view.get_queryset()) == []


@pytest.mark.parametrize(
    ("active", "data", "expected_log"),
    (
        (False, {"active": True}, "pretalx.question.activate"),
        (True, {"active": False}, "pretalx.question.deactivate"),
        (False, {"active": True, "help_text": "new"}, "pretalx.question.update"),
        (True, {"help_text": "new"}, "pretalx.question.update"),
    ),
    ids=["activate", "deactivate", "mixed", "no_active_change"],
)
def test_question_viewset_perform_update_log_type(active, data, expected_log):
    question = QuestionFactory(active=active, help_text="old")
    user = make_orga_user(question.event, can_change_event_settings=True)
    request = make_api_request(event=question.event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "partial_update"

    with scope(event=question.event):
        serializer = QuestionOrgaSerializer(
            instance=question, data=data, partial=True, context={"request": request}
        )
        assert serializer.is_valid(), serializer.errors
        view.perform_update(serializer)

        question.refresh_from_db()
        assert question.active is data.get("active", active)
        assert str(question.help_text) == data.get("help_text", "old")
        logs = list(question.logged_actions().values_list("action_type", flat=True))
        assert logs == [expected_log]
