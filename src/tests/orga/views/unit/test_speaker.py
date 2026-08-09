# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.orga.views.speaker import (
    SpeakerDetail,
    SpeakerExport,
    SpeakerInformationView,
    SpeakerList,
    SpeakerToggleArrived,
)
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    QuestionFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("get_params", "expect_biography"),
    (({}, False), ({"fulltext": "on", "q": "needle"}, True)),
)
def test_speaker_list_handle_search_biography_with_fulltext(
    event, get_params, expect_biography
):
    user = make_orga_user(event, can_change_submissions=True)
    named = SpeakerFactory(event=event, name="Needle")
    with_biography = SpeakerFactory(
        event=event, name="Other", biography="A needle in the bio"
    )
    request = make_request(event, user=user)
    request.GET = get_params
    view = make_view(SpeakerList, request)

    with scope(event=event):
        result = set(view.handle_search(SpeakerProfile.objects.all(), "needle", []))

    assert result == ({named, with_biography} if expect_biography else {named})


def test_speaker_list_get_queryset_annotates_counts(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    sub1.speakers.add(speaker)
    sub2.speakers.add(speaker)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0].submission_count == 2
    assert result[0].accepted_submission_count == 1


def test_speaker_list_get_queryset_filters_by_question_answer(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )
    AnswerFactory(question=question, speaker=speaker, answer="blue")
    other_speaker = SpeakerFactory(event=event)
    other_sub = SubmissionFactory(event=event)
    other_sub.speakers.add(other_speaker)

    request = make_request(event, user=user)
    request.GET = {"question": str(question.pk), "answer": "blue"}
    view = make_view(SpeakerList, request)

    result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0] == speaker


def test_speaker_list_get_queryset_filters_by_answer_option(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.CHOICES
    )
    option = AnswerOptionFactory(question=question, answer="green")
    answer = AnswerFactory(question=question, speaker=speaker)
    answer.options.set([option])
    other_speaker = SpeakerFactory(event=event)
    other_sub = SubmissionFactory(event=event)
    other_sub.speakers.add(other_speaker)

    request = make_request(event, user=user)
    request.GET = {"question": str(question.pk), "answer__options": str(option.pk)}
    view = make_view(SpeakerList, request)

    result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0] == speaker


def test_speaker_list_get_queryset_filters_by_unanswered(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )
    AnswerFactory(question=question, speaker=speaker, answer="blue")
    unanswered_speaker = SpeakerFactory(event=event)
    other_sub = SubmissionFactory(event=event)
    other_sub.speakers.add(unanswered_speaker)

    request = make_request(event, user=user)
    request.GET = {"question": str(question.pk), "unanswered": "true"}
    view = make_view(SpeakerList, request)

    result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0] == unanswered_speaker


def test_speaker_list_get_table_data(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    result = list(view.get_table_data())

    assert len(result) == 1
    assert result[0] == speaker


def test_speaker_list_short_questions(event):
    user = make_orga_user(event, can_change_submissions=True)
    short_q = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )
    QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.TEXT
    )
    QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    result = list(view.short_questions)

    assert result == [short_q]


@pytest.mark.parametrize(
    ("user_kwargs", "expected"),
    (
        ({"can_change_submissions": True}, True),
        ({"can_change_submissions": False, "is_reviewer": True}, False),
    ),
    ids=("orga", "reviewer"),
)
def test_speaker_list_get_table_kwargs_update_permission(event, user_kwargs, expected):
    user = make_orga_user(event, **user_kwargs)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SpeakerList, request)

    kwargs = view.get_table_kwargs()

    assert kwargs["has_update_permission"] is expected


def test_speaker_view_mixin_get_object(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerToggleArrived, request, code=speaker.code)

    result = view.get_object()

    assert result == speaker


def test_speaker_detail_submissions_property(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    SubmissionFactory(event=event)  # unrelated submission

    request = make_request(event, user=user)
    view = make_view(SpeakerDetail, request, code=speaker.code)

    result = set(view.submissions)

    assert result == {sub}


def test_speaker_detail_accepted_submissions_property(event):
    user = make_orga_user(event, can_change_submissions=True)
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    accepted.speakers.add(speaker)
    submitted.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SpeakerDetail, request, code=speaker.code)

    result = set(view.accepted_submissions)

    assert result == {accepted}


def test_speaker_information_view_get_queryset(event):
    info1 = SpeakerInformationFactory(event=event)
    info2 = SpeakerInformationFactory(event=event)
    SpeakerInformationFactory()

    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerInformationView, request)

    result = list(view.get_queryset())

    assert result == [info1, info2]


def test_speaker_export_exporters_limited_to_speaker_group(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(SpeakerExport, request)

    result = view.exporters()

    assert {exporter.identifier for exporter in result} == {
        "speakers.csv",
        "speaker-questions.csv",
    }
