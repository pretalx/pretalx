import pytest
from django_scopes import scope, scopes_disabled

from pretalx.api.serializers.question import (
    AnswerCreateSerializer,
    AnswerOptionCreateSerializer,
    AnswerOptionSerializer,
    AnswerSerializer,
    QuestionOrgaSerializer,
    QuestionSerializer,
)
from pretalx.api.views.question import (
    AnswerOptionViewSet,
    AnswerViewSet,
    QuestionViewSet,
)
from pretalx.submission.models import QuestionTarget, QuestionVariant
from tests.factories import (
    AnswerOptionFactory,
    QuestionFactory,
    ReviewPhaseFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "action"), (("POST", "create"), ("PUT", "update")))
def test_question_viewset_get_unversioned_serializer_class_returns_orga_for_unsafe_method(
    method, action
):
    """Non-safe methods return QuestionOrgaSerializer regardless of permissions."""
    with scopes_disabled():
        question = QuestionFactory()
    request = make_api_request(event=question.event)
    request._request.method = method
    view = make_view(QuestionViewSet, request)
    view.action = action

    result = view.get_unversioned_serializer_class()

    assert result is QuestionOrgaSerializer


@pytest.mark.django_db
def test_question_viewset_get_unversioned_serializer_class_returns_orga_for_user_with_update_perm():
    """Safe methods return QuestionOrgaSerializer when user has update (can_change_event_settings) permission."""
    with scopes_disabled():
        question = QuestionFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=question.event.organiser,
            all_events=True,
            can_change_event_settings=True,
        )
        team.members.add(user)
    request = make_api_request(event=question.event, user=user)
    request._request.method = "GET"
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    result = view.get_unversioned_serializer_class()

    assert result is QuestionOrgaSerializer


@pytest.mark.django_db
def test_question_viewset_get_unversioned_serializer_class_returns_public_for_anonymous():
    """Safe methods without update permission return the public QuestionSerializer."""
    with scopes_disabled():
        question = QuestionFactory()
    request = make_api_request(event=question.event)
    request._request.method = "GET"
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    result = view.get_unversioned_serializer_class()

    assert result is QuestionSerializer


@pytest.mark.django_db
def test_question_viewset_get_unversioned_serializer_class_returns_public_for_user_without_update_perm():
    """Safe methods for a user with can_change_submissions (but not can_change_event_settings) return QuestionSerializer."""
    with scopes_disabled():
        question = QuestionFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=question.event.organiser,
            all_events=True,
            can_change_submissions=True,
            can_change_event_settings=False,
        )
        team.members.add(user)
    request = make_api_request(event=question.event, user=user)
    request._request.method = "GET"
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    result = view.get_unversioned_serializer_class()

    assert result is QuestionSerializer


@pytest.mark.django_db
def test_question_viewset_get_queryset_orga_sees_all_questions():
    """An organiser with can_change_event_settings sees all questions, including inactive ones."""
    with scopes_disabled():
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

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert question_active in qs
    assert question_inactive in qs
    assert question_reviewer in qs


@pytest.mark.django_db
def test_question_viewset_get_queryset_anonymous_sees_only_public():
    """An anonymous user with schedule access sees only public, active questions."""
    with scopes_disabled():
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
            slot.schedule.freeze("v1", notify_speakers=False)
        event.is_public = True
        event.feature_flags["show_schedule"] = True
        event.save()

    request = make_api_request(event=event)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    # The default manager (event.questions) excludes inactive and reviewer questions.
    # is_public=True filter means only the public question is returned.
    assert question_public in qs
    assert question_private not in qs
    # Inactive questions are excluded by the default manager
    assert question_inactive not in qs
    # Reviewer questions are excluded by the default manager
    assert question_reviewer not in qs


@pytest.mark.django_db
def test_question_viewset_get_queryset_reviewer_sees_visible_and_targeted():
    """A reviewer (is_only_reviewer) sees reviewer-visible questions and reviewer-targeted questions."""
    with scopes_disabled():
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

        # Create a reviewer user (is_only_reviewer: only has is_reviewer permission)
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
        phase.activate()

    request = make_api_request(event=event, user=user)
    view = make_view(QuestionViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert question_visible in qs
    assert question_reviewer_target in qs
    assert question_hidden not in qs
    # Inactive questions are filtered out
    assert question_inactive not in qs


@pytest.mark.django_db
def test_question_viewset_get_queryset_excludes_other_events():
    """get_queryset only returns questions for the view's event."""
    with scopes_disabled():
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

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert question in qs
    assert other_question not in qs


@pytest.mark.django_db
def test_answeroption_viewset_get_unversioned_serializer_class_returns_create_for_create():
    """The create action returns AnswerOptionCreateSerializer."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
    request = make_api_request(event=question.event)
    view = make_view(AnswerOptionViewSet, request)
    view.action = "create"

    result = view.get_unversioned_serializer_class()

    assert result is AnswerOptionCreateSerializer


@pytest.mark.django_db
@pytest.mark.parametrize("action", ("list", "update", "retrieve"))
def test_answeroption_viewset_get_unversioned_serializer_class_returns_default_for_non_create(
    action,
):
    """Non-create actions return the default AnswerOptionSerializer."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
    request = make_api_request(event=question.event)
    view = make_view(AnswerOptionViewSet, request)
    view.action = action

    result = view.get_unversioned_serializer_class()

    assert result is AnswerOptionSerializer


@pytest.mark.django_db
def test_answeroption_viewset_get_queryset_returns_only_choice_options():
    """get_queryset only returns options for questions with CHOICES or MULTIPLE variant."""
    with scopes_disabled():
        choice_question = QuestionFactory(variant=QuestionVariant.CHOICES)
        event = choice_question.event
        multiple_question = QuestionFactory(
            event=event, variant=QuestionVariant.MULTIPLE
        )
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

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert choice_option in qs
    assert multiple_option in qs
    assert number_option not in qs
    assert string_option not in qs


@pytest.mark.django_db
def test_answeroption_viewset_get_queryset_respects_user_visibility():
    """get_queryset only returns options for questions the user can see."""
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.CHOICES, active=True, is_public=True
        )
        event = question.event
        option = AnswerOptionFactory(question=question)

    # Anonymous user without schedule access should not see any options
    request = make_api_request(event=event)
    view = make_view(AnswerOptionViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert option not in qs


@pytest.mark.django_db
def test_answeroption_viewset_get_queryset_excludes_other_events():
    """get_queryset only returns options for the view's event."""
    with scopes_disabled():
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

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert option in qs
    assert other_option not in qs


@pytest.mark.django_db
def test_answer_viewset_get_unversioned_serializer_class_returns_create_for_create():
    """The create action returns AnswerCreateSerializer."""
    with scopes_disabled():
        question = QuestionFactory()
    request = make_api_request(event=question.event)
    view = make_view(AnswerViewSet, request)
    view.action = "create"

    result = view.get_unversioned_serializer_class()

    assert result is AnswerCreateSerializer


@pytest.mark.django_db
@pytest.mark.parametrize("action", ("list", "update", "retrieve", "destroy"))
def test_answer_viewset_get_unversioned_serializer_class_returns_default_for_non_create(
    action,
):
    """Non-create actions return the default AnswerSerializer."""
    with scopes_disabled():
        question = QuestionFactory()
    request = make_api_request(event=question.event)
    view = make_view(AnswerViewSet, request)
    view.action = action

    result = view.get_unversioned_serializer_class()

    assert result is AnswerSerializer
