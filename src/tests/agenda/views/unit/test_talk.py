# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import Http404
from django_scopes import scope

from pretalx.agenda.recording import BaseRecordingProvider
from pretalx.agenda.signals import register_recording_provider
from pretalx.agenda.views.talk import (
    FeedbackView,
    TalkReviewView,
    TalkSocialMediaCard,
    TalkView,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_talk_mixin_get_queryset_filters_by_event(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    SubmissionFactory(state=SubmissionStates.CONFIRMED)  # different event

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        qs = view.get_queryset()
        result = list(qs)

    assert result == [submission]


def test_talk_mixin_object_lookup_case_insensitive(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code.lower())

    with scope(event=event):
        assert view.object == submission


def test_talk_mixin_submission_is_same_as_object(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.submission is view.object


def test_talk_mixin_get_permission_object_returns_submission(event):
    submission = SubmissionFactory(event=event)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.get_permission_object() == submission


@pytest.mark.parametrize(
    ("is_public", "expected"),
    ((True, True), (False, False)),
    ids=["public_event", "private_event"],
)
def test_talk_mixin_scheduling_information_visible(
    published_talk_slot, is_public, expected
):
    event = published_talk_slot.submission.event
    event.is_public = is_public
    event.save()

    request = make_request(event)
    view = make_view(TalkView, request, slug=published_talk_slot.submission.code)

    with scope(event=event):
        assert view.scheduling_information_visible is expected


@pytest.mark.parametrize(
    ("is_public", "expected"),
    ((True, False), (False, True)),
    ids=["public_event", "private_event"],
)
def test_talk_mixin_hide_speaker_links(published_talk_slot, is_public, expected):
    event = published_talk_slot.submission.event
    event.is_public = is_public
    event.save()

    request = make_request(event)
    view = make_view(TalkView, request, slug=published_talk_slot.submission.code)

    with scope(event=event):
        assert view.hide_speaker_links is expected


def test_talk_view_recording_empty_when_no_providers(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.recording == {}


def test_talk_view_recording_with_provider(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    class TestProvider(BaseRecordingProvider):
        def get_recording(self, submission):
            return {"iframe": "<iframe src='test'></iframe>", "csp_header": "test.com"}

    def handler(signal, sender, **kwargs):
        return TestProvider(sender)

    register_signal_handler(register_recording_provider, handler)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.recording == {
            "iframe": "<iframe src='test'></iframe>",
            "csp_header": "test.com",
        }


def test_talk_view_recording_skips_exception_response(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    def handler(signal, sender, **kwargs):
        raise ValueError("broken provider")

    register_signal_handler(register_recording_provider, handler)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.recording == {}


def test_talk_view_recording_skips_provider_without_iframe(
    register_signal_handler, event
):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    class TestProvider(BaseRecordingProvider):
        def get_recording(self, submission):
            return {"iframe": "", "csp_header": ""}

    def handler(signal, sender, **kwargs):
        return TestProvider(sender)

    register_signal_handler(register_recording_provider, handler)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.recording == {}


def test_talk_view_recording_iframe_with_provider(register_signal_handler, event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    class TestProvider(BaseRecordingProvider):
        def get_recording(self, submission):
            return {"iframe": "<iframe>video</iframe>", "csp_header": "cdn.example.com"}

    def handler(signal, sender, **kwargs):
        return TestProvider(sender)

    register_signal_handler(register_recording_provider, handler)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.recording_iframe() == "<iframe>video</iframe>"


def test_talk_view_recording_iframe_empty_when_no_recording(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.recording_iframe() is None


@pytest.mark.parametrize(
    ("use_speaker", "expected"),
    ((True, True), (False, False)),
    ids=["speaker", "other_user"],
)
def test_talk_view_is_speaker(event, use_speaker, expected):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    user = speaker.user if use_speaker else UserFactory()

    request = make_request(event, user=user)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.is_speaker() is expected


@pytest.mark.parametrize(
    ("abstract", "description", "expected"),
    (
        ("My abstract", "My description", "My abstract"),
        ("", "My description", "My description"),
    ),
    ids=["abstract-present", "description-fallback"],
)
def test_talk_view_submission_description(event, abstract, description, expected):
    submission = SubmissionFactory(
        event=event, abstract=abstract, description=description
    )

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.submission_description == expected


def test_talk_view_submission_description_fallback_to_generic(event):
    submission = SubmissionFactory(event=event, abstract="", description="")

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        desc = str(view.submission_description)
        assert submission.title in desc
        assert str(event.name) in desc


def test_talk_view_answers_splits_regular_and_icon(event):
    """answers and icon_answers correctly separate public answers by show_icon.
    show_icon is True when variant is URL and icon is set to a real value."""
    submission = SubmissionFactory(event=event)
    regular_q = QuestionFactory(
        event=event, is_public=True, variant="string", target="submission"
    )
    icon_q = QuestionFactory(
        event=event, is_public=True, variant="url", icon="github", target="submission"
    )
    regular_a = AnswerFactory(
        question=regular_q, submission=submission, answer="Regular"
    )
    icon_a = AnswerFactory(
        question=icon_q, submission=submission, answer="https://github.com/test"
    )

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        answers = view.answers
        icon_answers = view.icon_answers

    assert len(answers) == 1
    assert answers[0].pk == regular_a.pk
    assert len(icon_answers) == 1
    assert icon_answers[0].pk == icon_a.pk


def test_talk_view_answers_empty_when_no_public_answers(event):
    submission = SubmissionFactory(event=event)
    q = QuestionFactory(event=event, is_public=False, target="submission")
    AnswerFactory(question=q, submission=submission, answer="Private")

    request = make_request(event)
    view = make_view(TalkView, request, slug=submission.code)

    with scope(event=event):
        assert view.answers == []
        assert view.icon_answers == []


@pytest.mark.parametrize(
    ("enabled", "expected"), ((True, True), (False, False)), ids=["enabled", "disabled"]
)
def test_talk_review_view_has_permission_requires_feature_flag(enabled, expected):
    event = EventFactory(feature_flags={"submission_public_review": enabled})
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    request = make_request(event)
    view = make_view(TalkReviewView, request, slug=submission.review_code)

    assert view.has_permission() is expected


def test_talk_review_view_object_uses_review_code(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    request = make_request(event)
    view = make_view(TalkReviewView, request, slug=submission.review_code)

    with scope(event=event):
        assert view.object == submission


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.DRAFT,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
    ),
    ids=["submitted", "draft", "accepted", "confirmed"],
)
def test_talk_review_view_object_allows_valid_states(event, state):
    submission = SubmissionFactory(event=event, state=state)

    request = make_request(event)
    view = make_view(TalkReviewView, request, slug=submission.review_code)

    with scope(event=event):
        assert view.object == submission


@pytest.mark.parametrize(
    "state",
    (SubmissionStates.REJECTED, SubmissionStates.CANCELED, SubmissionStates.WITHDRAWN),
    ids=["rejected", "canceled", "withdrawn"],
)
def test_talk_review_view_object_404_for_invalid_states(event, state):
    submission = SubmissionFactory(event=event, state=state)

    request = make_request(event)
    view = make_view(TalkReviewView, request, slug=submission.review_code)

    with scope(event=event), pytest.raises(Http404):
        _ = view.object


def test_talk_review_view_hide_visibility_warning(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    request = make_request(event)
    view = make_view(TalkReviewView, request, slug=submission.review_code)

    assert view.hide_visibility_warning() is True


def test_talk_review_view_hide_speaker_links(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    request = make_request(event)
    view = make_view(TalkReviewView, request, slug=submission.review_code)

    assert view.hide_speaker_links() is True


def test_feedback_view_talk_returns_submission(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_request(event)
    view = make_view(FeedbackView, request, slug=submission.code)

    with scope(event=event):
        assert view.talk == submission


def test_feedback_view_speakers_returns_sorted_speakers(event):
    speaker_a = SpeakerFactory(event=event, user__name="Alice")
    speaker_b = SpeakerFactory(event=event, user__name="Bob")
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker_a, speaker_b)

    request = make_request(event)
    view = make_view(FeedbackView, request, slug=submission.code)

    with scope(event=event):
        speakers = list(view.speakers)
        assert [s.pk for s in speakers] == [speaker_a.pk, speaker_b.pk]


@pytest.mark.parametrize(
    ("use_speaker", "expected"),
    ((True, True), (False, False)),
    ids=["speaker", "other_user"],
)
def test_feedback_view_is_speaker(event, use_speaker, expected):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    user = speaker.user if use_speaker else UserFactory()

    request = make_request(event, user=user)
    view = make_view(FeedbackView, request, slug=submission.code)

    with scope(event=event):
        assert view.is_speaker is expected


def test_feedback_view_feedback_returns_feedback_for_speaker(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    fb_for_speaker = FeedbackFactory(talk=submission, speaker=speaker)
    fb_general = FeedbackFactory(talk=submission, speaker=None)
    other_speaker = SpeakerFactory(event=event)
    submission.speakers.add(other_speaker)
    FeedbackFactory(talk=submission, speaker=other_speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(FeedbackView, request, slug=submission.code)

    with scope(event=event):
        feedback = list(view.feedback)

    assert {f.pk for f in feedback} == {fb_for_speaker.pk, fb_general.pk}


def test_feedback_view_feedback_none_for_non_speaker(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    other_user = UserFactory()

    request = make_request(event, user=other_user)
    view = make_view(FeedbackView, request, slug=submission.code)

    with scope(event=event):
        assert view.feedback is None


def test_talk_social_media_card_get_image_returns_submission_image(event, make_image):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.image = make_image("talk.png")
    submission.save()

    request = make_request(event)
    view = make_view(TalkSocialMediaCard, request, slug=submission.code)

    with scope(event=event):
        image = view.get_image()
        assert image is not None


def test_talk_social_media_card_get_image_none_when_no_image(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    request = make_request(event)
    view = make_view(TalkSocialMediaCard, request, slug=submission.code)

    with scope(event=event):
        assert not view.get_image()
