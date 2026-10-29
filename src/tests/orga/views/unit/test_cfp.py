# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.http import Http404
from django.urls import resolve

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
    has_i18n_content,
    parse_dragsort_order,
)
from pretalx.submission.domain.queries.question import (
    question_answer_summary,
    question_scope_speakers,
)
from pretalx.submission.models import (
    QuestionTarget,
    Submission,
    SubmissionStates,
    SubmitterAccessCode,
)
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _editor(event):
    user = make_orga_user(event, can_change_event_settings=True)
    return make_view(CfPFlowEditor, make_request(event, user=user))


def test_cfp_text_detail_object_and_deadlines(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPTextDetail, request)

    assert view.get_object() == event.cfp
    assert view.different_deadlines is None

    deadline = dt.datetime(2025, 6, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    st = SubmissionTypeFactory(event=event, deadline=deadline)

    assert make_view(CfPTextDetail, request).different_deadlines == {deadline: [st]}


def test_question_view_get_queryset_answer_count_ignores_team_limits(event):
    question = QuestionFactory(event=event)
    AnswerFactory(question=question, submission=SubmissionFactory(event=event))
    AnswerFactory(question=question, submission=SubmissionFactory(event=event))
    teams = [
        TeamFactory(organiser=event.organiser, all_events=True),
        TeamFactory(organiser=event.organiser, all_events=True),
    ]
    question.limit_teams.add(*teams)
    user = make_orga_user(event, teams=teams)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [question]
    assert [q.answer_count for q in qs] == [2]


def test_question_view_get_queryset_answer_count_excludes_draft_submissions(event):
    question = QuestionFactory(event=event)
    AnswerFactory(question=question, submission=SubmissionFactory(event=event))
    AnswerFactory(
        question=question,
        submission=SubmissionFactory(event=event, state=SubmissionStates.DRAFT),
    )
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert [q.answer_count for q in qs] == [1]
    assert (
        qs[0].answer_count
        == question_answer_summary(
            question=question,
            talks=event.submissions.all(),
            speakers=question_scope_speakers(event),
        )["answer_count"]
    )


def test_question_view_get_queryset_answer_count_excludes_draft_only_speakers(event):
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    counted = SpeakerFactory(event=event)
    ignored = SpeakerFactory(event=event)
    SubmissionFactory(event=event).speakers.add(counted)
    SubmissionFactory(event=event, state=SubmissionStates.DRAFT).speakers.add(ignored)
    AnswerFactory(question=question, submission=None, speaker=counted)
    AnswerFactory(question=question, submission=None, speaker=ignored)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert [q.answer_count for q in qs] == [1]
    assert (
        qs[0].answer_count
        == question_answer_summary(
            question=question,
            talks=event.submissions.all(),
            speakers=question_scope_speakers(event),
        )["answer_count"]
    )


def test_question_view_list_urls(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    delete = make_view(QuestionView, request)
    delete.action = "delete"
    delete._next_url = None
    delete.namespace = "orga"
    delete.url_name = "cfp.questions"
    listing = make_view(QuestionView, request)
    listing.action = "list"
    listing.namespace = "orga"
    listing.url_name = "cfp.questions"

    assert delete.get_success_url() == event.cfp.urls.questions
    assert listing.get_create_url() == event.cfp.urls.new_question


@pytest.mark.parametrize(
    ("slug", "expected"),
    (
        ("sessions", QuestionTarget.SUBMISSION),
        ("speakers", QuestionTarget.SPEAKER),
        ("reviews", QuestionTarget.REVIEWER),
    ),
)
def test_question_view_target_comes_from_url(event, slug, expected):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request, target=slug)

    assert view.target == expected


@pytest.mark.parametrize("slug", (None, "", "nonsense", "submission"))
def test_question_view_target_rejects_unknown_slug(event, slug):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request, target=slug)

    with pytest.raises(Http404):
        view.target  # noqa: B018 -- accessing the property is the action under test


@pytest.mark.parametrize(
    ("target", "expected_review_settings"),
    ((QuestionTarget.SUBMISSION, False), (QuestionTarget.REVIEWER, True)),
)
def test_question_view_get_list_url_by_target(event, target, expected_review_settings):
    question = QuestionFactory(event=event, target=target)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request)
    view.action = "update"
    view.object = question
    view.namespace = "orga"
    view.url_name = "cfp.questions"

    url = view.get_list_url()

    if expected_review_settings:
        assert url == f"{event.orga_urls.review_settings}#tab-questions"
    else:
        assert url == event.cfp.urls.questions


def test_question_view_get_list_url_for_reviewer_create(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionView, request, target="reviews")
    view.action = "create"
    view.object = None
    view.namespace = "orga"
    view.url_name = "cfp.questions"

    assert view.get_list_url() == f"{event.orga_urls.review_settings}#tab-questions"


@pytest.mark.parametrize(
    ("order", "expected"),
    (
        ("3,1,2", [(0, 3), (1, 1), (2, 2)]),
        ("7", [(0, 7)]),
        ("3,x", None),
        ("-1,2", None),
        ("", None),
    ),
)
def test_parse_dragsort_order(order, expected):
    assert parse_dragsort_order(order) == expected


def _search_url(event, user, question, get_params=None):
    request = make_request(event, user=user)
    request.GET = get_params or {}
    view = make_view(QuestionView, request, pk=question.pk)
    view.object = question
    return view.base_search_url


def test_question_view_base_search_url_by_target(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission_q = QuestionFactory(event=event, target="submission")
    speaker_q = QuestionFactory(event=event, target="speaker")
    reviewer_q = QuestionFactory(event=event, target="reviewer")

    assert (
        _search_url(event, user, submission_q)
        == f"{event.orga_urls.submissions}?question_{submission_q.id}="
    )
    assert (
        _search_url(event, user, speaker_q)
        == f"{event.orga_urls.speakers}?question_{speaker_q.id}="
    )
    assert _search_url(event, user, reviewer_q) is None


def test_question_view_base_search_url_role_filters(event):
    question = QuestionFactory(event=event, target="submission")
    track = TrackFactory(event=event)
    st = SubmissionTypeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)

    accepted = _search_url(
        event,
        user,
        question,
        {"role": "accepted", "track": str(track.pk), "submission_type": str(st.pk)},
    )
    confirmed = _search_url(event, user, question, {"role": "confirmed"})

    assert "state=accepted" in accepted
    assert "state=confirmed" in accepted
    assert f"track={track.pk}" in accepted
    assert f"submission_type={st.pk}" in accepted
    assert f"question_{question.id}=" in accepted
    assert "state=confirmed" in confirmed
    assert "state=accepted" not in confirmed


def test_cfp_question_toggle_get_object(event):
    question = QuestionFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionToggle, request, pk=question.pk)

    obj = view.get_object()

    assert obj == question


def test_question_file_download_view(event):
    question = QuestionFactory(event=event, variant="file")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuestionFileDownloadView, request, pk=question.pk)

    assert view.question == question
    assert view.get_object() == question
    assert view.get_permission_object() == question
    assert (
        view.get_async_download_filename()
        == f"{event.slug}_question_{question.pk}_files.zip"
    )
    assert view.get_error_redirect_url() == question.urls.base


def test_cfp_question_remind_reminder_template(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(CfPQuestionRemind, request)

    template = view.reminder_template()

    assert template.role == "question.reminder"


def test_submission_type_view_get_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(SubmissionTypeView, request)
    view.action = "list"

    assert list(view.get_queryset()) == [event.cfp.default_type]


def test_submission_type_default_view(event):
    st = SubmissionTypeFactory(event=event, name="Workshop")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, path="/?next=/orga/event/")
    view = make_view(SubmissionTypeDefault, request, pk=st.pk)

    assert view.object == st
    assert str(view.action_text) == (
        "Are you sure you want to make “Workshop” the default session type?"
    )
    assert view.action_back_url == "/orga/event/"


def test_track_view_get_queryset(event):
    track = TrackFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(TrackView, request)
    view.action = "list"

    assert list(view.get_queryset()) == [track]


def test_access_code_view_get_queryset_and_send(event):
    code = SubmitterAccessCodeFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(AccessCodeView, request)
    view.action = "list"

    assert list(view.get_queryset()) == [code]
    assert make_view(AccessCodeSend, request, code=code.code).access_code == code


def test_access_code_view_get_context_data_detail_includes_submissions(event):
    code = SubmitterAccessCodeFactory(event=event)
    submission = SubmissionFactory(event=event, access_code=code)
    SubmissionFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.resolver_match = resolve(code.urls.base)
    view = make_view(AccessCodeView, request, code=code.code)
    view.action = "detail"
    view.object = code
    view.url_name = "cfp.access_code"
    view.namespace = "orga"

    ctx = view.get_context_data()

    assert list(ctx["submissions"]) == [submission]


def test_access_code_view_get_form_kwargs_with_track(event):
    track = TrackFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, path=f"?track={track.pk}")
    request.GET = {"track": str(track.pk)}
    view = make_view(AccessCodeView, request)
    view.action = "create"
    view.object = None
    view.model = SubmitterAccessCode

    kwargs = view.get_form_kwargs()

    assert kwargs.get("initial", {}).get("tracks") == [track]


@pytest.mark.parametrize(
    ("field_key", "expected"),
    (
        ("additional_speaker", "Additional speakers"),
        ("abstract", "Abstract"),
        ("totally_unknown_field", "Totally Unknown Field"),
    ),
)
def test_get_field_label(field_key, expected):
    assert str(get_field_label(field_key, Submission)) == expected


@pytest.mark.parametrize(
    ("use_tracks", "track_reason"),
    ((False, "tracks are disabled"), (True, "no tracks exist")),
    ids=("tracks-disabled", "no-tracks"),
)
def test_cfp_editor_mixin_auto_field_states_bare_event(use_tracks, track_reason):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})

    auto_hidden, auto_required = _editor(event).auto_field_states

    assert auto_hidden == {
        "submission_type": "only one option available",
        "content_locale": "only one language configured",
        "track": track_reason,
        "tags": "no public tags exist",
    }
    assert auto_required == set()


def test_cfp_editor_mixin_auto_field_states_configured_event():
    event = EventFactory(
        feature_flags={"use_tracks": True}, content_locales=["en", "de"]
    )
    SubmissionTypeFactory(event=event)
    TrackFactory(event=event)
    TagFactory(event=event, is_public=True)

    auto_hidden, auto_required = _editor(event).auto_field_states

    assert auto_hidden == {}
    assert auto_required == {"submission_type"}


def test_cfp_editor_mixin_get_step_context(event):
    view = _editor(event)

    assert view.get_step_context("nonexistent")["error"] == "Step not found"
    user_ctx = view.get_step_context(CfPFlow.STEP_USER)
    assert user_ctx["is_static"] is True
    assert user_ctx["fields"] == []
    questions_ctx = view.get_step_context(CfPFlow.STEP_QUESTIONS)
    assert questions_ctx["is_questions"] is True
    assert "submission_questions" in questions_ctx
    assert "speaker_questions" in questions_ctx
    info_ctx = view.get_step_context("info")
    assert info_ctx["is_static"] is False
    assert "available_fields" in info_ctx
    type_field = next(f for f in info_ctx["fields"] if f["key"] == "submission_type")
    assert type_field["form_field"] is None
    assert type_field["default_value"] == event.cfp.default_type
    profile_ctx = view.get_step_context("profile")
    assert profile_ctx["is_static"] is False
    assert "fields" in profile_ctx


def test_cfp_editor_mixin_helpers(event):
    active_q = QuestionFactory(event=event, target="submission", active=True)
    inactive_q = QuestionFactory(event=event, target="submission", active=False)
    view = _editor(event)

    class FakeStep:
        identifier = "custom_plugin_step"

    step = view.flow.steps_dict["info"]
    step_config = view.flow.get_step_config("info")
    step_config["fields"] = [{"key": "nonexistent_field_xyz"}, {"key": "title"}]

    assert [
        q["question_id"]
        for q in view._get_questions_by_target(QuestionTarget.SUBMISSION)
    ] == [active_q.pk]
    assert [
        q["question_id"]
        for q in view._get_questions_by_target(QuestionTarget.SUBMISSION, active=False)
    ] == [inactive_q.pk]
    assert view._get_preview_form(FakeStep()) is None
    field_keys = [f["key"] for f in view._get_step_fields(step, step_config)]
    assert "nonexistent_field_xyz" not in field_keys
    assert "title" in field_keys


def test_cfp_flow_editor_get_context_data(event):
    ctx = _editor(event).get_context_data()

    assert "steps" in ctx
    assert ctx["active_step"] == CfPFlow.STEP_INFO


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


def test_cfp_editor_field_label_and_initial(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(CfPEditorField, request, step="info", field_key="abstract")
    no_step = make_view(
        CfPEditorField, request, step="nonexistent", field_key="abstract"
    )

    assert str(view.field_label) == "Abstract"
    assert set(view._build_form_initial()) >= {"visibility", "label"}
    assert no_step.field_label == "abstract"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, False),
        ("", False),
        (0, False),
        ({}, False),
        ("hello", True),
        ("  ", False),
        ({"en": "hello"}, True),
        ({"en": "", "de": ""}, False),
        ({"en": "  ", "de": ""}, False),
        ({"en": "", "de": "Hallo"}, True),
        ({"en": None, "de": "Hallo"}, True),
    ),
)
def test_has_i18n_content(value, expected):
    assert has_i18n_content(value) is expected
