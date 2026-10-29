# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import Http404, QueryDict

from pretalx.cfp.views.user import (
    MailListView,
    ProfileView,
    SubmissionConfirmView,
    SubmissionDraftDiscardView,
    SubmissionInviteAcceptView,
    SubmissionsEditView,
    SubmissionsListView,
    SubmissionViewMixin,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    QuestionFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    UserFactory,
)
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("enabled", (True, False))
def test_profile_view_can_edit_speaker_matches_feature_flag(enabled):
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": enabled})
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    assert view.can_edit_speaker is enabled


def test_profile_view_questions_exist_with_speaker_questions(event):
    request = make_request(event, user=UserFactory())

    assert make_view(ProfileView, request).questions_exist() is False

    QuestionFactory(event=event, target="speaker")

    assert make_view(ProfileView, request).questions_exist() is True


def test_submission_view_mixin_get_object_matches_code_case_insensitively(event):
    submission = SubmissionFactory(event=event)
    request = make_request(event, user=UserFactory())

    view = make_view(SubmissionViewMixin, request, code=submission.code.lower())
    assert view.get_object() == submission

    view = make_view(SubmissionViewMixin, request, code="NONEXISTENT")
    with pytest.raises(Http404):
        view.get_object()


def test_submissions_list_view_shows_own_submissions_drafts_and_information(event):
    speaker = SpeakerFactory(event=event)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    confirmed.speakers.add(speaker)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    draft.speakers.add(speaker)
    SubmissionFactory(event=event)
    visible_info = SpeakerInformationFactory(event=event, target_group="accepted")
    hidden_info = SpeakerInformationFactory(event=event, target_group="accepted")
    hidden_info.limit_types.add(SubmissionTypeFactory(event=event))

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    assert list(view.get_queryset()) == [confirmed]
    assert view.drafts == [draft]
    assert list(view.information()) == [visible_info]


def test_submissions_edit_view_can_edit_submitted_with_invitations(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    invitation = SubmissionInvitationFactory(
        submission=submission, email="invited@example.com"
    )
    request = make_request(event, user=UserFactory())
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.can_edit is True
    assert list(view.invitations) == [invitation]


@pytest.mark.parametrize(
    ("max_speakers", "speaker_count", "invite_count", "expected"),
    (
        (None, 1, 0, True),
        (2, 1, 0, True),
        (2, 2, 0, False),
        (2, 1, 1, False),
        (3, 1, 1, True),
        (None, 1, 48, True),
        (None, 1, 49, False),
    ),
)
def test_submissions_edit_view_can_add_more_speakers(
    max_speakers, speaker_count, invite_count, expected
):
    cfp_fields = (
        {"additional_speaker": {"max": max_speakers}}
        if max_speakers is not None
        else {}
    )
    event = EventFactory(cfp__fields=cfp_fields)
    submission = SubmissionFactory(event=event)
    for _ in range(speaker_count):
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    for i in range(invite_count):
        SubmissionInvitationFactory(
            submission=submission, email=f"invite{i}@example.com"
        )

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.can_add_more_speakers == expected


@pytest.mark.parametrize(
    ("visibility", "expected_required"),
    (("do_not_ask", None), ("optional", False), ("required", True)),
)
def test_submission_confirm_view_get_form_availabilities_follow_cfp_config(
    visibility, expected_required
):
    event = EventFactory(cfp__fields={"availabilities": {"visibility": visibility}})
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    form = view.get_form()

    field = form.fields.get("availabilities")
    assert getattr(field, "required", None) is expected_required


def test_submission_draft_discard_view_get_object_only_returns_drafts(event):
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    request = make_request(event, user=UserFactory())

    view = make_view(SubmissionDraftDiscardView, request, code=draft.code)
    assert view.get_object() == draft

    view = make_view(SubmissionDraftDiscardView, request, code=submitted.code)
    with pytest.raises(Http404):
        view.get_object()


def test_mail_list_view_mails_returns_only_sent_mails_to_speaker(event):
    speaker = SpeakerFactory(event=event)
    sent_mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    sent_mail.to_speakers.add(speaker)
    draft_mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    draft_mail.to_speakers.add(speaker)

    speaker_view = make_view(MailListView, make_request(event, user=speaker.user))
    no_profile_view = make_view(MailListView, make_request(event, user=UserFactory()))

    assert list(speaker_view.mails()) == [sent_mail]
    assert list(no_profile_view.mails()) == []


def test_submission_invite_accept_view_can_accept_invite_true_for_valid_user(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    user = UserFactory()
    invitation = SubmissionInvitationFactory(submission=submission, email=user.email)

    request = make_request(event, user=user)
    view = make_view(
        SubmissionInviteAcceptView,
        request,
        code=submission.code,
        invitation=invitation.token,
    )

    assert view.can_accept_invite is True


def _make_signup_submission(
    *, capacity=None, signup_required=True, **submission_kwargs
):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=signup_required
    )
    return SubmissionFactory(
        event=event,
        submission_type=sub_type,
        attendee_signup_capacity=capacity,
        state=SubmissionStates.ACCEPTED,
        **submission_kwargs,
    )


def _signup_edit_view(submission):
    request = make_request(submission.event, user=UserFactory())
    return make_view(SubmissionsEditView, request, code=submission.code)


@pytest.mark.parametrize(
    ("feature_enabled", "type_requires", "state", "expected"),
    (
        (False, True, SubmissionStates.ACCEPTED, False),
        (True, False, SubmissionStates.ACCEPTED, False),
        (True, True, SubmissionStates.SUBMITTED, False),
        (True, True, SubmissionStates.ACCEPTED, True),
    ),
)
def test_submissions_edit_view_signup_enabled(
    feature_enabled, type_requires, state, expected
):
    event = EventFactory(feature_flags={"attendee_signup": feature_enabled})
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_requires
    )
    submission = SubmissionFactory(event=event, submission_type=sub_type, state=state)

    view = _signup_edit_view(submission)

    assert view.signup_enabled is expected


def test_submissions_edit_view_signup_props_none_when_disabled():
    event = EventFactory(feature_flags={"attendee_signup": False})
    submission = SubmissionFactory(event=event, attendee_signup_capacity=20)
    AttendeeSignupFactory(submission=submission)

    view = _signup_edit_view(submission)

    assert view.signup_attendee_count is None
    assert view.signup_capacity is None
    assert view.signup_table is None


def test_submissions_edit_view_signup_props_count_confirmed_signups():
    submission = _make_signup_submission(capacity=42)

    assert list(_signup_edit_view(submission).signup_table.rows) == []

    cancelled = AttendeeSignupFactory(
        submission=submission, state=AttendeeSignupStates.CANCELED
    )
    confirmed1 = AttendeeSignupFactory(submission=submission)
    confirmed2 = AttendeeSignupFactory(submission=submission)
    view = _signup_edit_view(submission)

    assert view.signup_attendee_count == 2
    assert view.signup_capacity == 42
    records = [row.record for row in view.signup_table.rows]
    assert records == [confirmed1, confirmed2, cancelled]


@pytest.mark.parametrize(
    ("capacity", "signups", "expected"), ((None, 0, None), (10, 3, 30), (2, 5, 100))
)
def test_submissions_edit_view_signup_capacity_percent(capacity, signups, expected):
    submission = _make_signup_submission(capacity=capacity)
    for _ in range(signups):
        AttendeeSignupFactory(submission=submission)

    view = _signup_edit_view(submission)

    assert view.signup_capacity_percent == expected
