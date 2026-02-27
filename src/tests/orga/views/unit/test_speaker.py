import pytest
from django_scopes import scopes_disabled

from pretalx.orga.views.speaker import (
    SpeakerDetail,
    SpeakerExport,
    SpeakerInformationView,
    SpeakerList,
    SpeakerPasswordReset,
    SpeakerToggleArrived,
)
from pretalx.submission.models import (
    Answer,
    QuestionTarget,
    QuestionVariant,
    SubmissionStates,
)
from tests.factories import (
    AnswerOptionFactory,
    QuestionFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("get_params", "expect_biography"),
    (({}, False), ({"fulltext": "on", "q": "something"}, True)),
)
def test_speaker_list_get_default_filters_biography_with_fulltext(
    event, get_params, expect_biography
):
    """Biography filter is only included when fulltext flag is enabled."""
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = get_params
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        filters = view.get_default_filters()

    assert ("biography__icontains" in filters) is expect_biography
    assert "name__icontains" in filters
    assert "user__email__icontains" in filters
    assert "user__name__icontains" in filters


@pytest.mark.django_db
def test_speaker_list_get_queryset_annotates_counts(event):
    """Queryset is annotated with submission_count and accepted_submission_count."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        sub1.speakers.add(speaker)
        sub2.speakers.add(speaker)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0].submission_count == 2
    assert result[0].accepted_submission_count == 1


@pytest.mark.django_db
def test_speaker_list_get_queryset_filters_by_question_answer(event):
    """Queryset can be filtered by text answer."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        question = QuestionFactory(
            event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
        )
        Answer.objects.create(question=question, speaker=speaker, answer="blue")
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(other_speaker)

    request = make_request(event, user=user)
    request.GET = {"question": str(question.pk), "answer": "blue"}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0] == speaker


@pytest.mark.django_db
def test_speaker_list_get_queryset_filters_by_answer_option(event):
    """Queryset can be filtered by choice question option."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        question = QuestionFactory(
            event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.CHOICES
        )
        option = AnswerOptionFactory(question=question, answer="green")
        answer = Answer.objects.create(question=question, speaker=speaker)
        answer.options.set([option])
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(other_speaker)

    request = make_request(event, user=user)
    request.GET = {"question": str(question.pk), "answer__options": str(option.pk)}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0] == speaker


@pytest.mark.django_db
def test_speaker_list_get_queryset_filters_by_unanswered(event):
    """Queryset can filter by speakers who have not answered a question."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        question = QuestionFactory(
            event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
        )
        Answer.objects.create(question=question, speaker=speaker, answer="blue")
        unanswered_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(unanswered_speaker)

    request = make_request(event, user=user)
    request.GET = {"question": str(question.pk), "unanswered": "true"}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0] == unanswered_speaker


@pytest.mark.django_db
def test_speaker_list_get_table_data(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        result = list(view.get_table_data())

    assert len(result) == 1
    assert result[0] == speaker


@pytest.mark.django_db
def test_speaker_list_short_questions(event):
    """short_questions property returns short-answer speaker questions."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        short_q = QuestionFactory(
            event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
        )
        QuestionFactory(
            event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.TEXT
        )
        QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
        )

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        result = list(view.short_questions)

    assert result == [short_q]


@pytest.mark.django_db
def test_speaker_list_get_table_kwargs_includes_permissions(event):
    """Table kwargs include has_arrived_permission and has_update_permission."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    with scopes_disabled():
        kwargs = view.get_table_kwargs()

    assert isinstance(kwargs["has_arrived_permission"], bool)
    assert isinstance(kwargs["has_update_permission"], bool)
    assert kwargs["short_questions"] == []


@pytest.mark.django_db
def test_speaker_view_mixin_get_object(event):
    """SpeakerViewMixin.get_object returns the speaker matching the code."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerToggleArrived, request, code=speaker.code)

    with scopes_disabled():
        result = view.get_object()

    assert result == speaker


@pytest.mark.django_db
def test_speaker_detail_submissions_property(event):
    """submissions property returns submissions for the speaker."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        SubmissionFactory(event=event)  # unrelated submission

    request = make_request(event, user=user)
    view = make_view(SpeakerDetail, request, code=speaker.code)

    with scopes_disabled():
        result = set(view.submissions)

    assert result == {sub}


@pytest.mark.django_db
def test_speaker_detail_accepted_submissions_property(event):
    """accepted_submissions only includes accepted/confirmed submissions."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        accepted.speakers.add(speaker)
        submitted.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerDetail, request, code=speaker.code)

    with scopes_disabled():
        result = set(view.accepted_submissions)

    assert result == {accepted}


@pytest.mark.django_db
def test_speaker_detail_get_success_url(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerDetail, request, code=speaker.code)

    with scopes_disabled():
        url = view.get_success_url()

    assert url == speaker.orga_urls.base


@pytest.mark.django_db
def test_speaker_detail_get_form_kwargs(event):
    """get_form_kwargs includes event, user, and is_orga."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerDetail, request, code=speaker.code)
    view.model = SpeakerDetail.model
    view.form_class = SpeakerDetail.form_class
    view.fields = None

    with scopes_disabled():
        kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event
    assert kwargs["user"] == speaker.user
    assert kwargs["is_orga"] is True


@pytest.mark.django_db
def test_speaker_password_reset_action_object_name(event):
    """action_object_name returns display name and email."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerPasswordReset, request, code=speaker.code)

    with scopes_disabled():
        result = view.action_object_name()

    assert result == f"{speaker.get_display_name()} ({speaker.user.email})"


@pytest.mark.django_db
def test_speaker_password_reset_action_back_url(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerPasswordReset, request, code=speaker.code)

    with scopes_disabled():
        url = view.action_back_url()

    assert url == speaker.orga_urls.base


@pytest.mark.django_db
def test_speaker_information_view_get_queryset(event):
    with scopes_disabled():
        info1 = SpeakerInformationFactory(event=event)
        info2 = SpeakerInformationFactory(event=event)
        SpeakerInformationFactory()

    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerInformationView, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [info1, info2]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected_permission"),
    (
        ("list", "person.list_speakerinformation"),
        ("detail", "person.orga_detail_speakerinformation"),
        ("create", "person.create_speakerinformation"),
        ("update", "person.update_speakerinformation"),
        ("delete", "person.delete_speakerinformation"),
    ),
)
def test_speaker_information_view_get_permission_required(
    event, action, expected_permission
):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerInformationView, request)
    view.action = action

    assert view.get_permission_required() == expected_permission


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("list", "Speaker Information Notes"),
        ("create", "Speaker Information Note"),
        ("update", "Speaker Information Note"),
    ),
)
def test_speaker_information_view_get_generic_title(event, action, expected):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerInformationView, request)
    view.action = action

    assert str(view.get_generic_title()) == expected


@pytest.mark.django_db
def test_speaker_export_get_form_kwargs(event):
    """get_form_kwargs passes event to the form."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerExport, request)
    view.form_class = SpeakerExport.form_class
    view.prefix = None
    view.initial = {}

    kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event


@pytest.mark.django_db
def test_speaker_export_exporters(event):
    """exporters returns only exporters in the 'speaker' group."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerExport, request)

    result = view.exporters()

    assert all(e.group == "speaker" for e in result)


@pytest.mark.django_db
def test_speaker_export_tablist(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerExport, request)

    result = view.tablist()

    assert set(result.keys()) == {"custom", "general", "api"}
