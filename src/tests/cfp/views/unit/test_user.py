# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import MagicMock

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


def test_profile_view_questions_exist_true_when_speaker_questions_present(event):
    QuestionFactory(event=event, target="speaker")
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    assert view.questions_exist() is True


def test_profile_view_questions_exist_false_when_no_speaker_questions(event):
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    assert view.questions_exist() is False


def test_submission_view_mixin_get_object_returns_submission(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionViewMixin, request, code=submission.code)

    result = view.get_object()

    assert result == submission


def test_submission_view_mixin_submission_property_returns_object(event):
    """The submission cached_property returns the same object as get_object."""
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionViewMixin, request, code=submission.code)

    assert view.submission == submission


def test_submission_view_mixin_get_object_404_for_wrong_code(event):
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionViewMixin, request, code="NONEXISTENT")

    with pytest.raises(Http404):
        view.get_object()


def test_submission_view_mixin_get_object_case_insensitive(event):
    submission = SubmissionFactory(event=event)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionViewMixin, request, code=submission.code.lower())

    result = view.get_object()

    assert result == submission


def test_submissions_list_view_get_queryset_filters_by_speaker(event):
    speaker = SpeakerFactory(event=event)
    my_submission = SubmissionFactory(event=event)
    my_submission.speakers.add(speaker)
    SubmissionFactory(event=event)  # other submission

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    result = list(view.get_queryset())

    assert result == [my_submission]


def test_submissions_list_view_drafts_returns_draft_submissions(event):
    speaker = SpeakerFactory(event=event)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    draft.speakers.add(speaker)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    submitted.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    result = list(view.drafts())

    assert result == [draft]


def test_submissions_list_view_information_filters_by_visibility(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    visible_info = SpeakerInformationFactory(event=event, target_group="accepted")
    SpeakerInformationFactory(event=event, target_group="submitters")

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    result = view.information()

    assert visible_info in result


def test_submissions_edit_view_can_edit_true_for_submitted(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.can_edit is True


def test_submissions_edit_view_invitations_returns_submission_invitations(event):
    submission = SubmissionFactory(event=event)
    invitation = SubmissionInvitationFactory(
        submission=submission, email="invited@example.com"
    )

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    result = list(view.invitations)

    assert result == [invitation]


@pytest.mark.parametrize(
    ("max_speakers", "speaker_count", "invite_count", "expected"),
    (
        (None, 1, 0, True),
        (2, 1, 0, True),
        (2, 2, 0, False),
        (2, 1, 1, False),
        (3, 1, 1, True),
    ),
)
def test_submissions_edit_view_can_add_more_speakers(
    max_speakers, speaker_count, invite_count, expected
):
    """can_add_more_speakers respects max_speakers limit including pending invitations."""
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


def test_submission_confirm_view_get_form_removes_availabilities_when_not_requested():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "do_not_ask"}})
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    form = view.get_form()

    assert "availabilities" not in form.fields


def test_submission_confirm_view_get_form_keeps_availabilities_when_requested():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    form = view.get_form()

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].required is False


def test_submission_confirm_view_get_form_requires_availabilities_when_required():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    form = view.get_form()

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].required is True


def test_submission_draft_discard_view_get_object_raises_404_for_non_draft(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionDraftDiscardView, request, code=submission.code)

    with pytest.raises(Http404):
        view.get_object()


def test_submission_draft_discard_view_get_object_returns_draft(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionDraftDiscardView, request, code=submission.code)

    result = view.get_object()

    assert result == submission


def test_mail_list_view_mails_returns_only_sent_mails(event):
    user = UserFactory()
    sent_mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    sent_mail.to_users.add(user)
    draft_mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    draft_mail.to_users.add(user)

    request = make_request(event, user=user)
    view = make_view(MailListView, request)

    result = list(view.mails())

    assert result == [sent_mail]


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


def _make_signup_event_and_submission(**event_kwargs):
    flags = event_kwargs.pop("feature_flags", {})
    flags = {"attendee_signup": True, **flags}
    event = EventFactory(feature_flags=flags, **event_kwargs)
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, state=SubmissionStates.ACCEPTED
    )
    return event, submission


def test_submissions_edit_view_signup_enabled_false_without_feature_flag():
    event = EventFactory(feature_flags={"attendee_signup": False})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_enabled is False


def test_submissions_edit_view_signup_enabled_false_when_submission_does_not_require():
    event = EventFactory(feature_flags={"attendee_signup": True})
    submission = SubmissionFactory(event=event)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_enabled is False


def test_submissions_edit_view_signup_enabled_true_when_required():
    _, submission = _make_signup_event_and_submission()

    user = UserFactory()
    request = make_request(submission.event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_enabled is True


def test_submissions_edit_view_signup_enabled_false_for_non_accepted_state():
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, state=SubmissionStates.SUBMITTED
    )

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_enabled is False


def test_submissions_edit_view_signup_attendee_count_none_when_disabled():
    event = EventFactory(feature_flags={"attendee_signup": False})
    submission = SubmissionFactory(event=event)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_attendee_count is None


def test_submissions_edit_view_signup_attendee_count_only_confirmed():
    _, submission = _make_signup_event_and_submission()
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission)
    AttendeeSignupFactory(submission=submission, state=AttendeeSignupStates.CANCELED)

    user = UserFactory()
    request = make_request(submission.event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_attendee_count == 2


def test_submissions_edit_view_signup_capacity_none_when_disabled():
    event = EventFactory(feature_flags={"attendee_signup": False})
    submission = SubmissionFactory(event=event, attendee_signup_capacity=20)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_capacity is None


def test_submissions_edit_view_signup_capacity_uses_override():
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        attendee_signup_capacity=42,
        state=SubmissionStates.ACCEPTED,
    )

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_capacity == 42


def test_submissions_edit_view_signup_capacity_percent_none_without_capacity():
    _, submission = _make_signup_event_and_submission()

    user = UserFactory()
    request = make_request(submission.event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_capacity_percent is None


def test_submissions_edit_view_signup_capacity_percent_calculation():
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        attendee_signup_capacity=10,
        state=SubmissionStates.ACCEPTED,
    )
    for _ in range(3):
        AttendeeSignupFactory(submission=submission)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_capacity_percent == 30


def test_submissions_edit_view_signup_capacity_percent_capped_at_100():
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        attendee_signup_capacity=2,
        state=SubmissionStates.ACCEPTED,
    )
    for _ in range(5):
        AttendeeSignupFactory(submission=submission)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_capacity_percent == 100


def test_submissions_edit_view_signup_table_none_when_disabled():
    event = EventFactory(feature_flags={"attendee_signup": False})
    submission = SubmissionFactory(event=event)
    AttendeeSignupFactory(submission=submission)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    assert view.signup_table is None


def test_submissions_edit_view_signup_table_orders_confirmed_before_cancelled():
    _, submission = _make_signup_event_and_submission()
    cancelled = AttendeeSignupFactory(
        submission=submission, state=AttendeeSignupStates.CANCELED
    )
    confirmed = AttendeeSignupFactory(submission=submission)

    user = UserFactory()
    request = make_request(submission.event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    records = [row.record for row in view.signup_table.rows]
    assert records == [confirmed, cancelled]


def test_submissions_edit_view_save_formset_skips_unchanged_initial_form(event):
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code="TEST")

    unchanged_form = MagicMock()
    unchanged_form.has_changed.return_value = False
    unchanged_form.instance.pk = 1

    formset = MagicMock()
    formset.initial_forms = [unchanged_form]
    formset.deleted_forms = []
    formset.extra_forms = []

    view.__dict__["formset"] = formset

    view.save_formset(MagicMock())

    unchanged_form.save.assert_not_called()
