import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.urls import resolve
from django_scopes import scopes_disabled

from pretalx.cfp.flow import CfPFlow
from pretalx.orga.views.cfp import (
    AccessCodeSend,
    AccessCodeView,
    CfPEditorField,
    CfPEditorStep,
    CfPFlowEditor,
    CfPQuestionRemind,
    CfPQuestionToggle,
    CfPTextDetail,
    QuestionFileDownloadView,
    QuestionView,
    SubmissionTypeDefault,
    SubmissionTypeView,
    TrackView,
    get_field_label,
)
from pretalx.submission.models import QuestionTarget, Submission, SubmitterAccessCode
from pretalx.submission.models.question import Answer
from tests.factories import (
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_cfp_text_detail_get_object_returns_cfp(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPTextDetail, request)

    with scopes_disabled():
        obj = view.get_object()

    assert obj == event.cfp


@pytest.mark.django_db
def test_cfp_text_detail_get_success_url(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPTextDetail, request)

    with scopes_disabled():
        view.object = event.cfp

    assert view.get_success_url() == event.cfp.urls.text


@pytest.mark.django_db
def test_cfp_text_detail_sform(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPTextDetail, request)
    view.permission_action = "edit"

    sform = view.sform

    assert sform.prefix == "settings"


@pytest.mark.django_db
def test_cfp_text_detail_different_deadlines_empty(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPTextDetail, request)

    with scopes_disabled():
        result = view.different_deadlines

    assert result is None


@pytest.mark.django_db
def test_cfp_text_detail_different_deadlines_with_types(event):
    """When submission types have different deadlines, they are returned."""
    deadline = dt.datetime(2025, 6, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    with scopes_disabled():
        st = SubmissionTypeFactory(event=event, deadline=deadline)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPTextDetail, request)

    with scopes_disabled():
        result = view.different_deadlines

    assert result == {deadline: [st]}


@pytest.mark.django_db
def test_question_view_get_queryset(event):
    with scopes_disabled():
        question = QuestionFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [question]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"), (("list", "Custom fields"), ("create", "New custom field"))
)
def test_question_view_get_generic_title(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = action

    assert str(view.get_generic_title()) == expected


@pytest.mark.django_db
def test_question_view_get_generic_title_with_instance(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, question="Favourite color?")
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "detail"

    title = str(view.get_generic_title(instance=question))

    assert "Favourite color?" in title


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("list", "submission.orga_list_question"),
        ("detail", "submission.orga_view_question"),
    ),
)
def test_question_view_get_permission_required(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = action

    assert view.get_permission_required() == expected


@pytest.mark.django_db
def test_question_view_get_success_url_delete(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "delete"
    view._next_url = None
    view.namespace = "orga"
    view.url_name = "cfp.questions"

    with scopes_disabled():
        url = view.get_success_url()

    assert url == event.cfp.urls.questions


@pytest.mark.django_db
def test_question_view_filter_form(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)

    with scopes_disabled():
        form = view.filter_form

    assert "role" in form.fields


@pytest.mark.django_db
def test_question_view_base_search_url_submission(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, target="submission")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(
        event, user=user, path=f"?role=accepted&question={question.pk}"
    )
    view = make_view(QuestionView, request, pk=question.pk)
    view.object = question

    url = view.base_search_url

    assert f"question={question.id}" in url


@pytest.mark.django_db
def test_question_view_base_search_url_speaker(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, target="speaker")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request, pk=question.pk)
    view.object = question

    url = view.base_search_url

    assert url == f"{event.orga_urls.speakers}?&question={question.id}&"


@pytest.mark.django_db
def test_question_view_base_search_url_reviewer_returns_none(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, target="reviewer")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request, pk=question.pk)
    view.object = question

    assert view.base_search_url is None


@pytest.mark.django_db
def test_cfp_question_toggle_get_object(event):
    with scopes_disabled():
        question = QuestionFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionToggle, request, pk=question.pk)

    with scopes_disabled():
        obj = view.get_object()

    assert obj == question


@pytest.mark.django_db
def test_question_file_download_view_resolves_to_question(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, variant="file")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionFileDownloadView, request, pk=question.pk)

    with scopes_disabled():
        assert view.question == question
        assert view.get_object() == question
        assert view.get_permission_object() == question


@pytest.mark.django_db
def test_question_file_download_get_async_download_filename(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, variant="file")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionFileDownloadView, request, pk=question.pk)

    with scopes_disabled():
        filename = view.get_async_download_filename()

    assert filename == f"{event.slug}_question_{question.pk}_files.zip"


@pytest.mark.django_db
def test_question_file_download_get_error_redirect_url(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, variant="file")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionFileDownloadView, request, pk=question.pk)

    with scopes_disabled():
        url = view.get_error_redirect_url()

    assert url == question.urls.base


@pytest.mark.django_db
def test_cfp_question_remind_get_form_kwargs(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionRemind, request)

    kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event


@pytest.mark.django_db
def test_cfp_question_remind_get_success_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionRemind, request)

    assert view.get_success_url() == event.orga_urls.outbox


@pytest.mark.django_db
def test_cfp_question_remind_submit_buttons(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionRemind, request)

    buttons = view.submit_buttons()

    assert len(buttons) == 1


@pytest.mark.django_db
def test_cfp_question_remind_reminder_template(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionRemind, request)

    with scopes_disabled():
        template = view.reminder_template()

    assert template.role == "question.reminder"


@pytest.mark.django_db
@pytest.mark.parametrize("target", ("submission", "speaker"))
def test_cfp_question_remind_get_missing_answers(event, target):
    with scopes_disabled():
        question = QuestionFactory(event=event, target=target)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)

    with scopes_disabled():
        submissions = event.submissions.all()
        missing = CfPQuestionRemind.get_missing_answers(
            questions=[question], person=speaker, submissions=submissions
        )

    assert missing == [question]


@pytest.mark.django_db
def test_submission_type_view_get_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(SubmissionTypeView, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert len(qs) == 1
    assert qs[0] == event.cfp.default_type


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"), (("list", "Session types"), ("create", "New session type"))
)
def test_submission_type_view_get_generic_title(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(SubmissionTypeView, request)
    view.action = action

    assert str(view.get_generic_title()) == expected


@pytest.mark.django_db
def test_submission_type_view_get_generic_title_with_instance(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(SubmissionTypeView, request)

    with scopes_disabled():
        title = str(view.get_generic_title(instance=event.cfp.default_type))

    assert str(event.cfp.default_type.name) in title


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("list", "submission.orga_list_submissiontype"),
        ("detail", "submission.orga_detail_submissiontype"),
    ),
)
def test_submission_type_view_get_permission_required(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(SubmissionTypeView, request)
    view.action = action

    assert view.get_permission_required() == expected


@pytest.mark.django_db
def test_submission_type_default_get_object(event):
    with scopes_disabled():
        st = SubmissionTypeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(SubmissionTypeDefault, request, pk=st.pk)

    with scopes_disabled():
        obj = view.get_object()

    assert obj == st


@pytest.mark.django_db
def test_track_view_get_queryset(event):
    with scopes_disabled():
        track = TrackFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(TrackView, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [track]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"), (("list", "Tracks"), ("create", "New track"))
)
def test_track_view_get_generic_title(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(TrackView, request)
    view.action = action

    assert str(view.get_generic_title()) == expected


@pytest.mark.django_db
def test_track_view_get_generic_title_with_instance(event):
    with scopes_disabled():
        track = TrackFactory(event=event, name="Security")
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(TrackView, request)

    title = str(view.get_generic_title(instance=track))

    assert "Security" in title


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"),
    (("list", "submission.orga_list_track"), ("detail", "submission.orga_view_track")),
)
def test_track_view_get_permission_required(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(TrackView, request)
    view.action = action

    assert view.get_permission_required() == expected


@pytest.mark.django_db
def test_access_code_view_get_queryset(event):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(AccessCodeView, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [code]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"), (("list", "Access codes"), ("create", "New access code"))
)
def test_access_code_view_get_generic_title(event, action, expected):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(AccessCodeView, request)
    view.action = action

    assert str(view.get_generic_title()) == expected


@pytest.mark.django_db
def test_access_code_view_get_generic_title_with_instance(event):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(AccessCodeView, request)

    title = str(view.get_generic_title(instance=code))

    assert code.code in title


@pytest.mark.django_db
def test_access_code_view_get_context_data_detail_includes_submissions(event):
    """The detail context for an access code includes a submissions queryset."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
        SubmissionFactory(event=event, access_code=code)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.resolver_match = resolve(code.urls.base)
    view = make_view(AccessCodeView, request, code=code.code)
    view.action = "detail"
    view.object = code
    view.url_name = "cfp.access_code"
    view.namespace = "orga"

    with scopes_disabled():
        ctx = view.get_context_data()

    assert "submissions" in ctx


@pytest.mark.django_db
def test_access_code_view_get_form_kwargs_with_track(event):
    with scopes_disabled():
        track = TrackFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, path=f"?track={track.pk}")
    request.GET = {"track": str(track.pk)}
    view = make_view(AccessCodeView, request)
    view.action = "create"
    view.object = None
    view.model = SubmitterAccessCode

    with scopes_disabled():
        kwargs = view.get_form_kwargs()

    assert kwargs.get("initial", {}).get("tracks") == [track]


@pytest.mark.django_db
def test_access_code_send_get_success_url(event):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(AccessCodeSend, request, code=code.code)

    assert view.get_success_url() == event.cfp.urls.access_codes


@pytest.mark.django_db
def test_access_code_send_get_object(event):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(AccessCodeSend, request, code=code.code)

    with scopes_disabled():
        obj = view.get_object()

    assert obj == code


@pytest.mark.django_db
def test_access_code_send_submit_buttons(event):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(AccessCodeSend, request, code=code.code)

    buttons = view.submit_buttons()

    assert len(buttons) == 1


@pytest.mark.django_db
def test_access_code_send_get_form_kwargs(event):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(AccessCodeSend, request, code=code.code)

    with scopes_disabled():
        view.object = code
        kwargs = view.get_form_kwargs()

    assert kwargs["user"] == user


def test_get_field_label_known_cfp_field():
    label = get_field_label("title", Submission)
    assert label


def test_get_field_label_unknown_field():
    label = get_field_label("totally_unknown_field", Submission)
    assert label == "Totally Unknown Field"


@pytest.mark.django_db
def test_cfp_editor_mixin_flow(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    flow = view.flow

    assert isinstance(flow, CfPFlow)


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_field_states_single_type(event):
    """With only one submission type, submission_type is auto-hidden."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, auto_required = view.auto_field_states

    assert "submission_type" in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_field_states_multiple_types(event):
    """With multiple submission types, submission_type is auto-required."""
    with scopes_disabled():
        SubmissionTypeFactory(event=event)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, auto_required = view.auto_field_states

    assert "submission_type" in auto_required
    assert "submission_type" not in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_hidden_tracks_disabled(event):
    event.feature_flags["use_tracks"] = False
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, _ = view.auto_field_states

    assert "track" in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_hidden_no_tracks(event):
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
        event.tracks.all().delete()
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, _ = view.auto_field_states

    assert "track" in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_hidden_no_public_tags(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, _ = view.auto_field_states

    assert "tags" in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_get_step_context_invalid(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    ctx = view.get_step_context("nonexistent")

    assert ctx["error"] == "Step not found"


@pytest.mark.django_db
def test_cfp_editor_mixin_get_step_context_user(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    ctx = view.get_step_context(CfPFlow.STEP_USER)

    assert ctx["is_static"] is True
    assert ctx["fields"] == []


@pytest.mark.django_db
def test_cfp_editor_mixin_get_step_context_questions(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        ctx = view.get_step_context(CfPFlow.STEP_QUESTIONS)

    assert ctx["is_questions"] is True
    assert "submission_questions" in ctx
    assert "speaker_questions" in ctx


@pytest.mark.django_db
def test_cfp_editor_mixin_get_step_context_info(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        ctx = view.get_step_context("info")

    assert "fields" in ctx
    assert "available_fields" in ctx
    assert ctx["is_static"] is False


@pytest.mark.django_db
def test_cfp_editor_mixin_get_questions_by_target(event):
    with scopes_disabled():
        QuestionFactory(event=event, target="submission", active=True)
        QuestionFactory(event=event, target="submission", active=False)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        active = view._get_questions_by_target(QuestionTarget.SUBMISSION, active=True)
        inactive = view._get_questions_by_target(
            QuestionTarget.SUBMISSION, active=False
        )

    assert len(active) == 1
    assert len(inactive) == 1


@pytest.mark.django_db
def test_cfp_flow_editor_get_context_data(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        ctx = view.get_context_data()

    assert "steps" in ctx
    assert ctx["active_step"] == CfPFlow.STEP_INFO


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("get_params", "expected_template"),
    (
        ({}, "orga/cfp/editor.html#step-content-full"),
        ({"edit_header": "1"}, "orga/cfp/editor.html#step-header-edit"),
    ),
)
def test_cfp_editor_step_get_template_names(event, get_params, expected_template):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    request.GET = get_params
    view = make_view(CfPEditorStep, request, step="info")

    assert view.get_template_names() == [expected_template]


@pytest.mark.django_db
def test_cfp_editor_field_step_id_and_field_key(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPEditorField, request, step="info", field_key="abstract")

    assert view.step_id == "info"
    assert view.field_key == "abstract"


@pytest.mark.django_db
def test_cfp_editor_field_field_label(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPEditorField, request, step="info", field_key="abstract")

    with scopes_disabled():
        label = view.field_label

    assert str(label) == "Abstract"


@pytest.mark.django_db
def test_cfp_editor_field_build_form_initial(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPEditorField, request, step="info", field_key="abstract")

    with scopes_disabled():
        initial = view._build_form_initial()

    assert set(initial.keys()) >= {"visibility", "label"}


@pytest.mark.django_db
def test_question_view_base_search_url_accepted_role_with_filters(event):
    """The base_search_url includes role, track and submission_type filters."""
    with scopes_disabled():
        question = QuestionFactory(event=event, target="submission")
        track = TrackFactory(event=event)
        st = SubmissionTypeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(
        event,
        user=user,
        path=f"?role=accepted&track={track.pk}&submission_type={st.pk}",
    )
    request.GET = {
        "role": "accepted",
        "track": str(track.pk),
        "submission_type": str(st.pk),
    }
    view = make_view(QuestionView, request, pk=question.pk)
    view.object = question

    url = view.base_search_url

    assert "state=accepted" in url
    assert "state=confirmed" in url
    assert f"track={track.pk}" in url
    assert f"submission_type={st.pk}" in url
    assert f"question={question.id}" in url


@pytest.mark.django_db
def test_question_view_base_search_url_confirmed_role(event):
    with scopes_disabled():
        question = QuestionFactory(event=event, target="submission")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, path="?role=confirmed")
    request.GET = {"role": "confirmed"}
    view = make_view(QuestionView, request, pk=question.pk)
    view.object = question

    url = view.base_search_url

    assert "state=confirmed" in url
    assert "state=accepted" not in url


@pytest.mark.django_db
def test_cfp_question_remind_get_missing_answers_speaker_answered(event):
    """An answered speaker question is not returned as missing."""
    with scopes_disabled():
        question = QuestionFactory(event=event, target="speaker")
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        Answer.objects.create(question=question, speaker=speaker, answer="something")

    with scopes_disabled():
        submissions = event.submissions.all()
        missing = CfPQuestionRemind.get_missing_answers(
            questions=[question], person=speaker, submissions=submissions
        )

    assert missing == []


@pytest.mark.django_db
def test_cfp_question_remind_get_missing_answers_multiple_questions(event):
    """Multiple questions with mixed missing/answered states return only missing ones."""
    with scopes_disabled():
        q_sub = QuestionFactory(event=event, target="submission")
        q_speaker = QuestionFactory(event=event, target="speaker")
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        Answer.objects.create(question=q_speaker, speaker=speaker, answer="answered")

    with scopes_disabled():
        submissions = event.submissions.all()
        missing = CfPQuestionRemind.get_missing_answers(
            questions=[q_sub, q_speaker], person=speaker, submissions=submissions
        )

    assert missing == [q_sub]


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_field_states_multiple_locales(event):
    """With multiple content locales, content_locale is not auto-hidden."""
    with scopes_disabled():
        event.content_locale_array = "en,de"
        event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, _ = view.auto_field_states

    assert "content_locale" not in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_field_states_tracks_exist(event):
    """With tracks enabled and existing, track is not auto-hidden."""
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
        TrackFactory(event=event)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, _ = view.auto_field_states

    assert "track" not in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_auto_field_states_public_tags_exist(event):
    """With public tags, the tags field is not auto-hidden."""
    with scopes_disabled():
        TagFactory(event=event, is_public=True)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        auto_hidden, _ = view.auto_field_states

    assert "tags" not in auto_hidden


@pytest.mark.django_db
def test_cfp_editor_mixin_get_step_context_profile(event):
    """Profile step returns a SpeakerProfileForm as preview form."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        ctx = view.get_step_context("profile")

    assert ctx["is_static"] is False
    assert "fields" in ctx


@pytest.mark.django_db
def test_cfp_editor_field_label_no_step(event):
    """When the step doesn't exist, field_label falls back to the raw key."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPEditorField, request, step="nonexistent", field_key="abstract")

    label = view.field_label

    assert label == "abstract"


@pytest.mark.django_db
def test_cfp_question_remind_get_missing_answers_reviewer_question_ignored(event):
    """A reviewer question is ignored because the loop only handles submission/speaker."""
    with scopes_disabled():
        q_reviewer = QuestionFactory(event=event, target="reviewer")
        q_sub = QuestionFactory(event=event, target="submission")
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)

    with scopes_disabled():
        submissions = event.submissions.all()
        missing = CfPQuestionRemind.get_missing_answers(
            questions=[q_reviewer, q_sub], person=speaker, submissions=submissions
        )

    assert missing == [q_sub]


@pytest.mark.django_db
def test_cfp_editor_mixin_get_preview_form_returns_none_for_plugin_step(event):
    """_get_preview_form returns None for steps other than info/profile."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    class FakeStep:
        identifier = "custom_plugin_step"

    result = view._get_preview_form(FakeStep())

    assert result is None


@pytest.mark.django_db
def test_cfp_editor_mixin_get_step_fields_skips_invalid_key(event):
    """Keys in config that aren't in step_fields are skipped."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPFlowEditor, request)

    with scopes_disabled():
        step = view.flow.steps_dict["info"]
        step_config = view.flow.get_step_config("info")
        step_config["fields"] = [{"key": "nonexistent_field_xyz"}, {"key": "title"}]
        fields = view._get_step_fields(step, step_config)

    field_keys = [f["key"] for f in fields]
    assert "nonexistent_field_xyz" not in field_keys
    assert "title" in field_keys
