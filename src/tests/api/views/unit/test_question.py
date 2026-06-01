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
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.domain.review import activate_review_phase
from pretalx.submission.models import QuestionTarget, QuestionVariant
from tests.factories import (
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewPhaseFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_question_viewset_get_queryset_orga_sees_all_questions():
    question_active = QuestionFactory(active=True)
    event = question_active.event
    question_inactive = QuestionFactory(event=event, active=False)
    question_reviewer = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True
    )
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)

    request = make_api_request(event=event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert question_active in qs
    assert question_inactive in qs
    assert question_reviewer in qs


def test_question_viewset_get_queryset_anonymous_sees_only_public():
    question_public = QuestionFactory(active=True, is_public=True)
    event = question_public.event
    question_private = QuestionFactory(event=event, active=True, is_public=False)
    question_inactive = QuestionFactory(event=event, active=False, is_public=True)
    question_reviewer = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True, is_public=True
    )

    # Make the event public with a published schedule to give anonymous users
    # the list_question permission via is_agenda_visible
    slot = TalkSlotFactory(submission__event=event, is_visible=True)
    with scope(event=event):
        freeze_schedule(slot.schedule, "v1", notify_speakers=False)

    request = make_api_request(event=event)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    # The default manager (event.questions) excludes inactive and reviewer questions.
    # is_public=True filter means only the public question is returned.
    assert question_public in qs
    assert question_private not in qs
    # Inactive questions are excluded by the default manager
    assert question_inactive not in qs
    # Reviewer questions are excluded by the default manager
    assert question_reviewer not in qs


def test_question_viewset_get_queryset_reviewer_sees_visible_and_targeted():
    question_visible = QuestionFactory(active=True, is_visible_to_reviewers=True)
    event = question_visible.event
    question_reviewer_target = QuestionFactory(
        event=event,
        target=QuestionTarget.REVIEWER,
        active=True,
        is_visible_to_reviewers=False,
    )
    question_hidden = QuestionFactory(
        event=event,
        active=True,
        is_visible_to_reviewers=False,
        target=QuestionTarget.SUBMISSION,
    )
    question_inactive = QuestionFactory(
        event=event, active=False, is_visible_to_reviewers=True
    )

    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=False,
    )
    team.members.add(user)

    # Activate a review phase with can_see_speaker_names (needed for can_view_speaker_names)
    phase = ReviewPhaseFactory(event=event, can_see_speaker_names=True)
    activate_review_phase(phase)

    request = make_api_request(event=event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert question_visible in qs
    assert question_reviewer_target in qs
    assert question_hidden not in qs
    # Inactive questions are filtered out
    assert question_inactive not in qs


def test_question_viewset_get_queryset_excludes_other_events():
    question = QuestionFactory(active=True)
    other_question = QuestionFactory(active=True)
    user = UserFactory()
    team = TeamFactory(
        organiser=question.event.organiser,
        all_events=True,
        can_change_event_settings=True,
    )
    team.members.add(user)

    request = make_api_request(event=question.event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert question in qs
    assert other_question not in qs


def test_answeroption_viewset_get_unversioned_serializer_class_returns_create_for_create():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    request = make_api_request(event=question.event)
    view = make_view(AnswerOptionViewSet, request)
    view.action = "create"

    result = view.get_unversioned_serializer_class()

    assert result is AnswerOptionCreateSerializer


@pytest.mark.parametrize("action", ("list", "update", "retrieve"))
def test_answeroption_viewset_get_unversioned_serializer_class_returns_default_for_non_create(
    action,
):
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    request = make_api_request(event=question.event)
    view = make_view(AnswerOptionViewSet, request)
    view.action = action

    result = view.get_unversioned_serializer_class()

    assert result is AnswerOptionSerializer


def test_answeroption_viewset_get_queryset_returns_only_choice_options():
    choice_question = QuestionFactory(variant=QuestionVariant.CHOICES)
    event = choice_question.event
    multiple_question = QuestionFactory(event=event, variant=QuestionVariant.MULTIPLE)
    number_question = QuestionFactory(event=event, variant=QuestionVariant.NUMBER)
    string_question = QuestionFactory(event=event, variant=QuestionVariant.STRING)

    choice_option = AnswerOptionFactory(question=choice_question)
    multiple_option = AnswerOptionFactory(question=multiple_question)
    number_option = AnswerOptionFactory(question=number_question)
    string_option = AnswerOptionFactory(question=string_question)

    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)

    request = make_api_request(event=event, user=user)
    view = make_view(AnswerOptionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert choice_option in qs
    assert multiple_option in qs
    assert number_option not in qs
    assert string_option not in qs


def test_answeroption_viewset_get_queryset_respects_user_visibility():
    question = QuestionFactory(
        variant=QuestionVariant.CHOICES,
        active=True,
        is_public=True,
        event=EventFactory(is_public=False),
    )
    option = AnswerOptionFactory(question=question)

    # Anonymous user without schedule access should not see any options
    request = make_api_request(event=question.event)
    view = make_view(AnswerOptionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert option not in qs


def test_answeroption_viewset_get_queryset_excludes_other_events():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    event = question.event
    option = AnswerOptionFactory(question=question)

    other_question = QuestionFactory(variant=QuestionVariant.CHOICES)
    other_option = AnswerOptionFactory(question=other_question)

    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)

    request = make_api_request(event=event, user=user)
    view = make_view(AnswerOptionViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert option in qs
    assert other_option not in qs


def _make_question_view_and_request(question):
    user = UserFactory()
    team = TeamFactory(
        organiser=question.event.organiser,
        all_events=True,
        can_change_event_settings=True,
    )
    team.members.add(user)
    request = make_api_request(event=question.event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "partial_update"
    return view, request


def _bind_serializer(question, request, data):
    serializer = QuestionOrgaSerializer(
        instance=question, data=data, partial=True, context={"request": request}
    )
    assert serializer.is_valid(), serializer.errors
    return serializer


def test_question_viewset_perform_update_active_only_emits_single_activate_log():
    question = QuestionFactory(active=False)
    view, request = _make_question_view_and_request(question)

    with scope(event=question.event):
        serializer = _bind_serializer(question, request, {"active": True})
        view.perform_update(serializer)

        question.refresh_from_db()
        assert question.active is True
        logs = list(question.logged_actions().values_list("action_type", flat=True))
        assert logs == ["pretalx.question.activate"]


def test_question_viewset_perform_update_active_only_deactivate_log():
    question = QuestionFactory(active=True)
    view, request = _make_question_view_and_request(question)

    with scope(event=question.event):
        serializer = _bind_serializer(question, request, {"active": False})
        view.perform_update(serializer)

        question.refresh_from_db()
        assert question.active is False
        logs = list(question.logged_actions().values_list("action_type", flat=True))
        assert logs == ["pretalx.question.deactivate"]


def test_question_viewset_perform_update_mixed_change_emits_single_update_log():
    question = QuestionFactory(active=False, help_text="old")
    view, request = _make_question_view_and_request(question)

    with scope(event=question.event):
        serializer = _bind_serializer(
            question, request, {"active": True, "help_text": "new"}
        )
        view.perform_update(serializer)

        question.refresh_from_db()
        assert question.active is True
        assert str(question.help_text) == "new"
        logs = list(question.logged_actions().values_list("action_type", flat=True))
        assert logs == ["pretalx.question.update"]


def test_question_viewset_perform_update_no_active_change_emits_update_log():
    question = QuestionFactory(active=True, help_text="old")
    view, request = _make_question_view_and_request(question)

    with scope(event=question.event):
        serializer = _bind_serializer(question, request, {"help_text": "new"})
        view.perform_update(serializer)

        question.refresh_from_db()
        assert str(question.help_text) == "new"
        logs = list(question.logged_actions().values_list("action_type", flat=True))
        assert logs == ["pretalx.question.update"]
