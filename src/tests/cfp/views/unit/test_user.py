from unittest.mock import MagicMock

import pytest
from django.http import Http404, QueryDict
from django_scopes import scopes_disabled

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
from pretalx.mail.models import QueuedMailStates
from pretalx.submission.models import SubmissionInvitation, SubmissionStates
from tests.factories import (
    QuestionFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    UserFactory,
)
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_profile_view_can_edit_speaker_true_when_feature_enabled(event):
    """can_edit_speaker returns True when speakers_can_edit_submissions is enabled."""
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    assert view.can_edit_speaker is True


@pytest.mark.django_db
def test_profile_view_can_edit_speaker_false_when_feature_disabled(event):
    """can_edit_speaker returns False when speakers_can_edit_submissions is disabled."""
    event.feature_flags["speakers_can_edit_submissions"] = False
    event.save()
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    assert view.can_edit_speaker is False


@pytest.mark.django_db
def test_profile_view_questions_exist_true_when_speaker_questions_present(event):
    """questions_exist returns True when speaker-targeted questions exist."""
    with scopes_disabled():
        QuestionFactory(event=event, target="speaker")
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    with scopes_disabled():
        assert view.questions_exist() is True


@pytest.mark.django_db
def test_profile_view_questions_exist_false_when_no_speaker_questions(event):
    """questions_exist returns False when no speaker-targeted questions exist."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(ProfileView, request)

    with scopes_disabled():
        assert view.questions_exist() is False


@pytest.mark.django_db
def test_submission_view_mixin_get_object_returns_submission(event):
    """get_object returns the submission matching the code kwarg."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionViewMixin, request, code=submission.code)

    with scopes_disabled():
        result = view.get_object()

    assert result == submission


@pytest.mark.django_db
def test_submission_view_mixin_submission_property_returns_object(event):
    """The submission cached_property returns the same object as get_object."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionViewMixin, request, code=submission.code)

    with scopes_disabled():
        assert view.submission == submission


@pytest.mark.django_db
def test_submission_view_mixin_get_object_404_for_wrong_code(event):
    """get_object raises Http404 for a non-existent submission code."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionViewMixin, request, code="NONEXISTENT")

    with pytest.raises(Http404), scopes_disabled():
        view.get_object()


@pytest.mark.django_db
def test_submission_view_mixin_get_object_case_insensitive(event):
    """get_object matches submission code case-insensitively."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionViewMixin, request, code=submission.code.lower())

    with scopes_disabled():
        result = view.get_object()

    assert result == submission


@pytest.mark.django_db
def test_submissions_list_view_get_queryset_filters_by_speaker(event):
    """get_queryset returns only submissions where the user is a speaker."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        my_submission = SubmissionFactory(event=event)
        my_submission.speakers.add(speaker)
        SubmissionFactory(event=event)  # other submission

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [my_submission]


@pytest.mark.django_db
def test_submissions_list_view_drafts_returns_draft_submissions(event):
    """drafts property returns only DRAFT submissions for the current user."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(speaker)
        submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submitted.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    with scopes_disabled():
        result = list(view.drafts())

    assert result == [draft]


@pytest.mark.django_db
def test_submissions_list_view_information_filters_by_visibility(event):
    """information property returns only information items the user can see."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        visible_info = SpeakerInformationFactory(event=event, target_group="accepted")
        SpeakerInformationFactory(event=event, target_group="submitters")

    request = make_request(event, user=speaker.user)
    view = make_view(SubmissionsListView, request)

    with scopes_disabled():
        result = view.information()

    assert visible_info in result


@pytest.mark.django_db
def test_submissions_edit_view_can_edit_true_for_submitted(event):
    """can_edit returns True for a submission in SUBMITTED state."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    with scopes_disabled():
        assert view.can_edit is True


@pytest.mark.django_db
def test_submissions_edit_view_invitations_returns_submission_invitations(event):
    """invitations property returns invitations for the submission."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="invited@example.com"
        )

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    with scopes_disabled():
        result = list(view.invitations)

    assert result == [invitation]


@pytest.mark.django_db
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
    event, max_speakers, speaker_count, invite_count, expected
):
    """can_add_more_speakers respects max_speakers limit including pending invitations."""
    with scopes_disabled():
        if max_speakers is not None:
            event.cfp.fields["additional_speaker"] = {"max": max_speakers}
        event.cfp.save()
        submission = SubmissionFactory(event=event)
        for _ in range(speaker_count):
            speaker = SpeakerFactory(event=event)
            submission.speakers.add(speaker)
        for i in range(invite_count):
            SubmissionInvitation.objects.create(
                submission=submission, email=f"invite{i}@example.com"
            )

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code=submission.code)

    with scopes_disabled():
        assert view.can_add_more_speakers == expected


@pytest.mark.django_db
def test_submission_confirm_view_get_form_removes_availabilities_when_not_requested(
    event,
):
    """get_form removes the availabilities field when the CfP doesn't request them."""
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "do_not_ask"}
        event.cfp.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    with scopes_disabled():
        form = view.get_form()

    assert "availabilities" not in form.fields


@pytest.mark.django_db
def test_submission_confirm_view_get_form_keeps_availabilities_when_requested(event):
    """get_form keeps the availabilities field when the CfP requests them."""
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "optional"}
        event.cfp.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    with scopes_disabled():
        form = view.get_form()

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].required is False


@pytest.mark.django_db
def test_submission_confirm_view_get_form_requires_availabilities_when_required(event):
    """get_form marks availabilities as required when the CfP requires them."""
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "required"}
        event.cfp.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        submission.speakers.add(speaker)

    request = make_request(event, user=speaker.user)
    request.method = "GET"
    request.POST = QueryDict()
    view = make_view(SubmissionConfirmView, request, code=submission.code)

    with scopes_disabled():
        form = view.get_form()

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].required is True


@pytest.mark.django_db
def test_submission_draft_discard_view_get_object_raises_404_for_non_draft(event):
    """get_object raises Http404 when the submission is not in DRAFT state."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionDraftDiscardView, request, code=submission.code)

    with pytest.raises(Http404), scopes_disabled():
        view.get_object()


@pytest.mark.django_db
def test_submission_draft_discard_view_get_object_returns_draft(event):
    """get_object returns the submission when it is in DRAFT state."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)

    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionDraftDiscardView, request, code=submission.code)

    with scopes_disabled():
        result = view.get_object()

    assert result == submission


@pytest.mark.django_db
def test_mail_list_view_mails_returns_only_sent_mails(event):
    """mails property returns only mails with SENT state for the current user."""
    with scopes_disabled():
        user = UserFactory()
        sent_mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        sent_mail.to_users.add(user)
        draft_mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        draft_mail.to_users.add(user)

    request = make_request(event, user=user)
    view = make_view(MailListView, request)

    with scopes_disabled():
        result = list(view.mails())

    assert result == [sent_mail]


@pytest.mark.django_db
def test_submission_invite_accept_view_can_accept_invite_true_for_valid_user(event):
    """can_accept_invite returns True for a logged-in user with permission."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        user = UserFactory()
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email=user.email
        )

    request = make_request(event, user=user)
    view = make_view(
        SubmissionInviteAcceptView,
        request,
        code=submission.code,
        invitation=invitation.token,
    )

    with scopes_disabled():
        assert view.can_accept_invite is True


@pytest.mark.django_db
def test_submissions_edit_view_save_formset_skips_unchanged_initial_form(event):
    """save_formset skips initial forms that are not deleted and not changed."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(SubmissionsEditView, request, code="TEST")

    unchanged_form = MagicMock()
    unchanged_form.has_changed.return_value = False
    unchanged_form.instance.pk = 1

    formset = MagicMock()
    formset.is_valid.return_value = True
    formset.initial_forms = [unchanged_form]
    formset.deleted_forms = []
    formset.extra_forms = []

    view.__dict__["formset"] = formset

    result = view.save_formset(MagicMock())

    assert result is True
    unchanged_form.save.assert_not_called()
