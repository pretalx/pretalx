# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from contextlib import suppress

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope

from pretalx.submission.models import SubmissionStates, SubmitterAccessCode


@pytest.mark.django_db
def test_can_see_submission_list(speaker_client, submission):
    response = speaker_client.get(submission.event.urls.user_submissions, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text


@pytest.mark.django_db
def test_can_see_submission(speaker_client, submission):
    response = speaker_client.get(submission.urls.user_base, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text


@pytest.mark.django_db
def test_orga_gets_redirected_from_speaker_view(orga_client, submission):
    response = orga_client.get(submission.urls.user_base, follow=False)
    assert response.status_code == 302
    assert response.url == submission.orga_urls.base


@pytest.mark.django_db
def test_cannot_see_other_submission(speaker_client, other_submission):
    response = speaker_client.get(other_submission.urls.user_base, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_can_confirm_submission(speaker_client, accepted_submission):
    response = speaker_client.get(accepted_submission.urls.confirm, follow=True)
    accepted_submission.refresh_from_db()
    assert response.status_code == 200
    assert accepted_submission.state == SubmissionStates.ACCEPTED
    response = speaker_client.post(accepted_submission.urls.confirm, follow=True)
    accepted_submission.refresh_from_db()
    assert response.status_code == 200
    assert accepted_submission.state == SubmissionStates.CONFIRMED


@pytest.mark.django_db
def test_cannot_confirm_confirmed_submission(speaker_client, confirmed_submission):
    response = speaker_client.get(confirmed_submission.urls.confirm, follow=True)
    confirmed_submission.refresh_from_db()
    assert response.status_code == 200
    assert confirmed_submission.state == SubmissionStates.CONFIRMED
    response = speaker_client.post(confirmed_submission.urls.confirm, follow=True)
    confirmed_submission.refresh_from_db()
    assert response.status_code == 200
    assert confirmed_submission.state == SubmissionStates.CONFIRMED


@pytest.mark.django_db
def test_cannot_confirm_submitted_submission(speaker_client, submission):
    response = speaker_client.get(submission.urls.confirm, follow=True)
    submission.refresh_from_db()
    assert response.status_code == 200
    assert submission.state == SubmissionStates.SUBMITTED
    response = speaker_client.post(submission.urls.confirm, follow=True)
    submission.refresh_from_db()
    assert response.status_code == 200
    assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_can_reconfirm_submission(speaker_client, accepted_submission):
    accepted_submission.state = SubmissionStates.CONFIRMED
    accepted_submission.save()
    response = speaker_client.get(accepted_submission.urls.confirm, follow=True)
    accepted_submission.refresh_from_db()
    assert response.status_code == 200
    assert accepted_submission.state == SubmissionStates.CONFIRMED


@pytest.mark.django_db
def test_cannot_confirm_rejected_submission(other_speaker_client, rejected_submission):
    rejected_submission.state = SubmissionStates.REJECTED
    rejected_submission.save()
    response = other_speaker_client.get(rejected_submission.urls.confirm, follow=True)
    rejected_submission.refresh_from_db()
    assert response.status_code == 200
    assert rejected_submission.state == SubmissionStates.REJECTED


@pytest.mark.django_db
def test_can_withdraw_submission(speaker_client, submission):
    response = speaker_client.get(submission.urls.withdraw, follow=True)
    submission.refresh_from_db()
    assert response.status_code == 200
    assert submission.state == SubmissionStates.SUBMITTED
    response = speaker_client.post(submission.urls.withdraw, follow=True)
    submission.refresh_from_db()
    assert response.status_code == 200
    assert submission.state == SubmissionStates.WITHDRAWN


@pytest.mark.django_db
def test_cannot_withdraw_accepted_submission(speaker_client, accepted_submission):
    response = speaker_client.get(accepted_submission.urls.withdraw, follow=True)
    accepted_submission.refresh_from_db()
    assert response.status_code == 200
    assert accepted_submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_can_discard_draft_proposal(speaker_client, submission):
    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.save()
    response = speaker_client.get(submission.urls.discard, follow=True)
    assert response.status_code == 200
    response = speaker_client.post(submission.urls.discard, follow=True)
    assert response.status_code == 200
    with scope(event=submission.event):
        assert not submission.event.submissions.filter(pk=submission.pk).exists()


@pytest.mark.django_db
def test_cannot_discard_non_draft_proposal(speaker_client, submission):
    response = speaker_client.get(submission.urls.discard, follow=True)
    assert response.status_code == 404
    response = speaker_client.post(submission.urls.discard, follow=True)
    assert response.status_code == 404
    with scope(event=submission.event):
        assert submission.event.submissions.filter(pk=submission.pk).exists()


@pytest.mark.django_db
def test_can_edit_submission(speaker_client, submission, resource, other_resource):
    with scope(event=submission.event):
        assert submission.resources.count() == 2
        resource_one = submission.resources.first()
        resource_two = submission.resources.last()
        assert submission.title in str(resource_one)
        f = SimpleUploadedFile("testfile.txt", b"file_content")
        data = {
            "title": "Ein ganz neuer Titel",
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "slot_count": submission.slot_count,
            "resource-0-id": resource_one.id,
            "resource-0-description": "new resource name",
            "resource-0-resource": resource_one.resource,
            "resource-1-id": resource_two.id,
            "resource-1-DELETE": True,
            "resource-1-description": resource_two.description,
            "resource-1-resource": resource_two.resource,
            "resource-2-id": "",
            "resource-2-description": "new resource",
            "resource-2-resource": f,
            "resource-TOTAL_FORMS": 3,
            "resource-INITIAL_FORMS": 2,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)
    assert response.status_code == 200
    with scope(event=submission.event):
        assert submission.resources.count() == 2
        submission.refresh_from_db()
        resource_one.refresh_from_db()
        new_resource = submission.resources.exclude(pk=resource_one.pk).first()
        assert submission.title == "Ein ganz neuer Titel", response.text
        assert submission.resources.count() == 2
        assert new_resource.description == "new resource"
        assert new_resource.resource.read() == b"file_content"
        assert not submission.resources.filter(pk=resource_two.pk).exists()


@pytest.mark.django_db
def test_speaker_can_edit_submission_logs_consolidated(
    speaker_client, submission, question
):
    with scope(event=submission.event):
        submission.event.feature_flags["speakers_can_edit_submissions"] = True
        submission.event.save()
        question.question_required = "optional"
        question.save()
        log_count = submission.logged_actions().count()
        old_title = submission.title

        data = {
            "title": "Completely New Title",
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": "New description",
            "abstract": submission.abstract,
            "notes": submission.notes,
            "slot_count": submission.slot_count,
            f"question_{question.pk}": "50",
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)
    assert response.status_code == 200

    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.title == "Completely New Title"
        logs = submission.logged_actions()
        assert logs.count() == log_count + 1
        update_log = logs.filter(action_type="pretalx.submission.update").first()
        assert update_log
        assert update_log.changes
        assert update_log.changes["title"]["old"] == old_title
        assert update_log.changes["title"]["new"] == "Completely New Title"
        question_key = f"question-{question.pk}"
        assert update_log.changes[question_key]["old"] is None
        assert update_log.changes[question_key]["new"] == "50"


@pytest.mark.django_db
def test_can_edit_slot_count(speaker_client, submission):
    with scope(event=submission.event):
        submission.event.feature_flags["present_multiple_times"] = True
        submission.event.save()
        data = {
            "title": "Ein ganz neuer Titel",
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "slot_count": 13,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.slot_count == 13


@pytest.mark.django_db
def test_cannot_edit_confirmed_slot_count(speaker_client, confirmed_submission):
    submission = confirmed_submission
    submission.event.feature_flags["present_multiple_times"] = True
    submission.event.save()
    with scope(event=submission.event):
        data = {
            "title": "Ein ganz neuer Titel",
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "slot_count": 13,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.slot_count != 13


@pytest.mark.django_db
def test_cannot_edit_rejected_submission(other_speaker_client, rejected_submission):
    title = rejected_submission.title
    data = {
        "title": "Ein ganz neuer Titel",
        "submission_type": rejected_submission.submission_type.pk,
        "content_locale": rejected_submission.content_locale,
        "description": rejected_submission.description,
        "abstract": rejected_submission.abstract,
        "notes": rejected_submission.notes,
        "resource-TOTAL_FORMS": 0,
        "resource-INITIAL_FORMS": 0,
        "resource-MIN_NUM_FORMS": 0,
        "resource-MAX_NUM_FORMS": 1000,
    }
    response = other_speaker_client.post(
        rejected_submission.urls.user_base, follow=True, data=data
    )
    assert response.status_code == 200
    rejected_submission.refresh_from_db()
    assert rejected_submission.title == title


@pytest.mark.django_db
def test_can_edit_submission_type(speaker_client, submission, event):
    with scope(event=submission.event):
        new_type = event.submission_types.create(name="Other", default_duration=13)
        data = {
            "title": "Ein ganz neuer Titel",
            "submission_type": new_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.submission_type == new_type


@pytest.mark.django_db
def test_cannot_edit_submission_type_after_acceptance(
    speaker_client, submission, event
):
    with scope(event=submission.event):
        submission.accept()
        new_type = event.submission_types.create(name="Other", default_duration=13)
        data = {
            "title": "Ein ganz neuer Titel",
            "submission_type": new_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.submission_type != new_type


@pytest.mark.django_db
def test_cannot_edit_accepted_submission_when_feature_disabled(
    speaker_client, accepted_submission
):
    """Test that accepted submissions cannot be edited when speakers_can_edit_submissions is disabled"""
    with scope(event=accepted_submission.event):
        # First verify the submission is normally editable when accepted
        assert accepted_submission.editable is True

        # Disable the feature flag
        accepted_submission.event.feature_flags["speakers_can_edit_submissions"] = False
        accepted_submission.event.save()

        # Now it should not be editable (need to clear the cached property)
        accepted_submission.refresh_from_db()
        # Clear the cached property - Django's cached_property uses the property name as the cache key
        try:
            del accepted_submission.editable
        except AttributeError:
            pass  # Property wasn't cached yet
        assert accepted_submission.editable is False

        # Try to edit via POST request
        data = {
            "title": "Should not change",
            "submission_type": accepted_submission.submission_type.pk,
            "content_locale": accepted_submission.content_locale,
            "description": accepted_submission.description,
            "abstract": accepted_submission.abstract,
            "notes": accepted_submission.notes,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
        original_title = accepted_submission.title
        response = speaker_client.post(
            accepted_submission.urls.user_base, follow=True, data=data
        )
        assert response.status_code == 200

        # Verify the submission was not changed
        accepted_submission.refresh_from_db()
        assert accepted_submission.title == original_title


@pytest.mark.django_db
def test_draft_submission_still_editable_when_feature_disabled(
    speaker_client, submission
):
    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.save()
        submission.event.feature_flags["speakers_can_edit_submissions"] = False
        submission.event.save()
        submission.refresh_from_db()

        with suppress(AttributeError):
            del submission.editable
        assert submission.editable is True

        data = {
            "title": "Changed draft title",
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
        response = speaker_client.post(
            submission.urls.user_base, follow=True, data=data
        )
        assert response.status_code == 200
        submission.refresh_from_db()
        assert submission.title == "Changed draft title"


@pytest.mark.django_db
def test_can_edit_profile(speaker, event, speaker_client):
    response = speaker_client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.get(event=event).biography == "Ruling since forever."
        assert speaker.name == "Lady Imperator"
    response = speaker_client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.get(event=event).biography == "Ruling since forever."
        assert speaker.name == "Lady Imperator"


@pytest.mark.django_db
def test_must_provide_availabilities(speaker, event, speaker_client):
    event.cfp.fields["availabilities"]["visibility"] = "required"
    event.cfp.save()
    response = speaker_client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.get(event=event).biography != "Ruling since forever."
    response = speaker_client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
            "availabilities": '{"availabilities": []}',
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.get(event=event).biography != "Ruling since forever."


@pytest.mark.django_db
def test_can_edit_login_info(speaker, event, speaker_client):
    response = speaker_client.post(
        event.urls.user,
        data={
            "old_password": "speakerpwd1!",
            "email": "new_email@speaker.org",
            "password": "",
            "password_repeat": "",
            "form": "login",
        },
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.email == "new_email@speaker.org"


@pytest.mark.django_db
def test_can_edit_login_info_wrong_password(speaker, event, speaker_client):
    response = speaker_client.post(
        event.urls.user,
        data={
            "old_password": "speakerpwd23!",
            "email": "new_email@speaker.org",
            "password": "",
            "password_repeat": "",
            "form": "login",
        },
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.email != "new_email@speaker.org"


@pytest.mark.django_db
def test_can_edit_and_update_speaker_answers(
    speaker,
    event,
    speaker_question,
    speaker_boolean_question,
    speaker_client,
    speaker_text_question,
    speaker_file_question,
):
    with scope(event=event):
        answer = speaker.answers.filter(question_id=speaker_question.pk).first()
        assert not answer
    f = SimpleUploadedFile("testfile.txt", b"file_content")
    response = speaker_client.post(
        event.urls.user,
        data={
            f"question_{speaker_question.id}": "black as the night",
            f"question_{speaker_boolean_question.id}": "True",
            f"question_{speaker_file_question.id}": f,
            f"question_{speaker_text_question.id}": "Green is totally the best color.",
            "form": "questions",
        },
        follow=True,
    )
    assert response.status_code == 200

    with scope(event=event):
        answer = speaker.answers.get(question_id=speaker_question.pk)
        assert answer.answer == "black as the night"
        assert (
            speaker.answers.get(question_id=speaker_boolean_question.pk).answer
            == "True"
        )
        assert (
            speaker.answers.get(question_id=speaker_text_question.pk).answer
            == "Green is totally the best color."
        )

        file_answer = speaker.answers.get(question_id=speaker_file_question.pk)
        assert file_answer.answer.startswith("file://")
        assert file_answer.answer_file.read() == b"file_content"
        assert (settings.MEDIA_ROOT / file_answer.answer_file.name).exists()

    response = speaker_client.post(
        event.urls.user,
        data={
            f"question_{speaker_question.id}": "green as the sky",
            "form": "questions",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        answer.refresh_from_db()
        assert answer.answer == "green as the sky"

    response = speaker_client.post(
        event.urls.user,
        data={
            f"question_{speaker_question.id}": "green as the sky",
            "form": "questions",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        answer.refresh_from_db()
        assert answer.answer == "green as the sky"


@pytest.mark.django_db
def test_cannot_delete_profile_on_first_try(speaker, event, speaker_client):
    with scope(event=event):
        assert speaker.profiles.get(event=event).biography != ""
    response = speaker_client.post(event.urls.user_delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.get(event=event).biography != ""
        assert speaker.name != "Deleted User"


@pytest.mark.django_db
def test_can_delete_profile(speaker, event, speaker_client):
    with scope(event=event):
        assert speaker.profiles.get(event=event).biography != ""
    response = speaker_client.post(
        event.urls.user_delete, data={"really": True}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        speaker.refresh_from_db()
        assert speaker.profiles.get(event=event).biography == ""
        assert speaker.name == "Deleted User"
        assert speaker.email.startswith("deleted_user")
        assert speaker.email.endswith("@localhost")


@pytest.mark.django_db
def test_can_change_locale(multilingual_event, client):
    first_response = client.get(multilingual_event.cfp.urls.public, follow=True)
    assert "submission" in first_response.text
    assert "Kontakt" not in first_response.text
    second_response = client.get(
        reverse("cfp:locale.set", kwargs={"event": multilingual_event.slug})
        + f"?locale=de&next=/{multilingual_event.slug}/",
        follow=True,
    )
    assert "Kontakt" in second_response.text


@pytest.mark.django_db
def test_can_change_locale_with_queryparam(multilingual_event, client):
    first_response = client.get(multilingual_event.cfp.urls.public, follow=True)
    assert "submission" in first_response.text
    assert "Kontakt" not in first_response.text
    second_response = client.get(
        reverse("cfp:locale.set", kwargs={"event": multilingual_event.slug})
        + f"?locale=de&next=/{multilingual_event.slug}/?foo=bar",
        follow=True,
    )
    assert "Kontakt" in second_response.text


@pytest.mark.django_db
def test_persists_changed_locale(multilingual_event, orga_user, orga_client):
    assert orga_user.locale == "en"
    response = orga_client.get(
        reverse("cfp:locale.set", kwargs={"event": multilingual_event.slug})
        + f"?locale=de&next=/{multilingual_event.slug}/",
        follow=True,
    )
    orga_user.refresh_from_db()
    assert response.status_code == 200
    assert orga_user.locale == "de"


@pytest.mark.django_db
def test_can_invite_speaker(speaker_client, submission):
    djmail.outbox = []
    response = speaker_client.get(
        submission.urls.invite, follow=True, data={"email": "invalidemail"}
    )
    assert response.status_code == 200
    data = {
        "speaker": "other@speaker.org",
        "subject": "Please join!",
        "text": "C'mon, it will be fun!",
    }
    response = speaker_client.post(submission.urls.invite, follow=True, data=data)
    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["other@speaker.org"]


@pytest.mark.django_db
def test_can_accept_invitation(orga_client, submission):
    assert submission.speakers.count() == 1
    response = orga_client.post(submission.urls.accept_invitation, follow=True)
    submission.refresh_from_db()
    assert response.status_code == 200
    assert submission.speakers.count() == 2


@pytest.mark.django_db
def test_wrong_acceptance_link(orga_client, submission):
    assert submission.speakers.count() == 1
    response = orga_client.post(
        submission.urls.accept_invitation + "olololol", follow=True
    )
    submission.refresh_from_db()
    assert response.status_code == 404
    assert submission.speakers.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("get_availability", ("optional", "do_not_ask"))
def test_submission_accept(speaker_client, submission, get_availability):
    submission.event.cfp.fields["availabilities"]["visibility"] = get_availability
    submission.event.cfp.save()
    submission.state = SubmissionStates.ACCEPTED
    submission.save()

    response = speaker_client.post(submission.urls.confirm, follow=True)
    submission.refresh_from_db()

    assert response.status_code == 200
    assert submission.state == SubmissionStates.CONFIRMED


@pytest.mark.django_db
def test_submission_accept_with_missing_availability(speaker_client, submission):
    submission.event.cfp.fields["availabilities"]["visibility"] = "required"
    submission.event.cfp.save()
    submission.state = SubmissionStates.ACCEPTED
    submission.save()

    response = speaker_client.post(submission.urls.confirm, follow=True)
    submission.refresh_from_db()

    assert response.status_code == 200
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_accept_nologin(client, submission):
    submission.state = SubmissionStates.ACCEPTED
    submission.save()

    response = client.post(submission.urls.confirm, follow=True)
    submission.refresh_from_db()

    assert response.status_code == 200
    assert response.redirect_chain[-1][1] == 302
    assert "login/?next=" in response.redirect_chain[-1][0]
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_accept_wrong_code(client, submission):
    submission.state = SubmissionStates.ACCEPTED
    submission.save()

    assert submission.code in submission.urls.confirm
    response = client.post(
        submission.urls.confirm.replace(submission.code, "foo"), follow=True
    )

    assert response.status_code == 200
    assert response.redirect_chain[-1][1] == 302
    assert "login/?next=" in response.redirect_chain[-1][0]


@pytest.mark.django_db
def test_submission_withdraw(speaker_client, submission):
    djmail.outbox = []
    submission.state = SubmissionStates.SUBMITTED
    submission.save()

    response = speaker_client.post(submission.urls.withdraw, follow=True)
    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.WITHDRAWN
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_submission_withdraw_if_accepted(speaker_client, submission):
    djmail.outbox = []
    with scope(event=submission.event):
        submission.accept()

    response = speaker_client.post(submission.urls.withdraw, follow=True)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.WITHDRAWN
        assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_submission_withdraw_if_confirmed(speaker_client, submission):
    with scope(event=submission.event):
        submission.accept()
        submission.confirm()

    response = speaker_client.post(submission.urls.withdraw, follow=True)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.state != SubmissionStates.WITHDRAWN


@pytest.mark.django_db
def test_submission_withdraw_if_rejected(speaker_client, submission):
    with scope(event=submission.event):
        submission.reject()

    response = speaker_client.post(submission.urls.withdraw, follow=True)
    assert response.status_code == 200
    with scope(event=submission.event):
        submission.refresh_from_db()
        assert submission.state != SubmissionStates.WITHDRAWN


@pytest.mark.django_db
def test_draft_submission_prevented_when_access_code_required(
    speaker_client, submission, track
):

    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.track = track
        submission.save()

        submission.track.requires_access_code = True
        submission.track.save()

        assert not submission.editable

        data = {
            "action": "dedraft",
            "title": submission.title,
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
        response = speaker_client.post(
            submission.urls.user_base, data=data, follow=True
        )

        assert response.status_code == 200
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.DRAFT


@pytest.mark.django_db
def test_draft_submission_allowed_with_access_code(
    speaker_client, speaker, submission, track, answer
):

    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.track = track
        submission.access_code = SubmitterAccessCode.objects.create(
            event=submission.event, code="VALID123", track=submission.track
        )
        submission.save()
        answer.question.active = True
        answer.question.save()
        assert submission.answers.all().count() == 1

        submission.track.requires_access_code = True
        submission.track.save()

        data = {
            "action": "dedraft",
            "title": submission.title,
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            f"question_{answer.question.pk}": answer.answer,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
        response = speaker_client.post(submission.urls.user_base, data=data)

        # redirect to cfp flow
        assert response.status_code == 302
        url = response.url
        response = speaker_client.get(url)

        # redirect to first cfp flow form
        assert response.status_code == 302
        url = response.url
        response = speaker_client.get(url)
        assert response.status_code == 200

        from bs4 import BeautifulSoup

        for _step in "info", "question", "profile":
            soup = BeautifulSoup(response.render().content, "html.parser")
            form = soup.find_all("form")[1]
            form_data = {}
            for input_tag in form.find_all("input"):
                form_data[input_tag.get("name")] = input_tag.get("value", "")
            for input_tag in form.find_all("textarea"):
                form_data[input_tag.get("name")] = input_tag.text
            form_data["action"] = "submit"
            response = speaker_client.post(url, data=form_data)
            assert response.status_code == 302
            url = response.url
            response = speaker_client.get(url)
            assert response.status_code == 200

        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.access_code.is_valid
        assert submission.answers.all().count() == 1


@pytest.mark.django_db
def test_draft_submission_prevented_when_submission_type_requires_access_code(
    speaker_client, speaker, submission
):
    with scope(event=submission.event):
        submission.state = SubmissionStates.DRAFT
        submission.save()
        submission.submission_type.requires_access_code = True
        submission.submission_type.save()

        data = {
            "action": "dedraft",
            "title": submission.title,
            "submission_type": submission.submission_type.pk,
            "content_locale": submission.content_locale,
            "description": submission.description,
            "abstract": submission.abstract,
            "notes": submission.notes,
            "resource-TOTAL_FORMS": 0,
            "resource-INITIAL_FORMS": 0,
            "resource-MIN_NUM_FORMS": 0,
            "resource-MAX_NUM_FORMS": 1000,
        }
        response = speaker_client.post(
            submission.urls.user_base, data=data, follow=True
        )

        assert response.status_code == 200
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.DRAFT


@pytest.mark.parametrize("max_uses,exhausted", ((1, True), (2, False)))
@pytest.mark.django_db
def test_draft_with_deadline_access_code_exhausted(
    event, access_code, submission, max_uses, exhausted
):

    event.cfp.deadline = now() - dt.timedelta(days=1)
    event.cfp.save()

    with scope(event=event):
        submission.state = "draft"
        submission.access_code = access_code
        submission.save()
        access_code.maximum_uses = max_uses
        access_code.redeemed = 1
        access_code.save()

        assert access_code.is_valid is not exhausted
        assert access_code.time_valid

        assert (
            submission.editable
        ), "Draft should be editable even after access code redemptions are exhausted"


@pytest.mark.django_db
def test_draft_with_deadline_access_code_expired(event, access_code, submission):
    event.cfp.deadline = now() - dt.timedelta(days=1)
    event.cfp.save()
    access_code.valid_until = now() - dt.timedelta(hours=1)
    access_code.save()

    with scope(event=event):
        submission.state = "draft"
        submission.access_code = access_code
        submission.save()

        assert not access_code.is_valid
        assert not access_code.time_valid
        assert (
            not submission.editable
        ), "Draft should not be editable after access code time limit expires"


@pytest.mark.parametrize("max_uses,exhausted", ((1, True), (2, False)))
@pytest.mark.django_db
def test_draft_with_track_access_code_exhausted(
    event, speaker, access_code, submission, track, max_uses, exhausted
):
    """Test that a draft for a track requiring access code CAN still be edited
    even after the access code is exhausted (redemption count reached)."""
    with scope(event=event):
        track.requires_access_code = True
        track.save()
        access_code.track = track
        access_code.maximum_uses = max_uses
        access_code.redeemed = 1
        access_code.save()
        submission.state = "draft"
        submission.track = track
        submission.access_code = access_code
        submission.save()

        assert access_code.is_valid is not exhausted
        assert access_code.time_valid

        assert (
            submission.editable
        ), "Draft should be editable even after track access code redemptions are exhausted"


@pytest.mark.django_db
def test_access_code_redeemed_on_draft_creation(event, client, access_code):
    event.cfp.deadline = now() - dt.timedelta(days=1)
    event.cfp.save()
    access_code.maximum_uses = 5
    access_code.redeemed = 0
    access_code.save()

    with scope(event=event):
        submission_type = event.cfp.default_type.id

    url = f"/test/submit/?access_code={access_code.code}"
    response = client.get(url, follow=True)
    assert response.status_code == 200
    current_url = response.redirect_chain[-1][0]
    info_data = {
        "title": "Test Draft",
        "content_locale": "en",
        "description": "Description",
        "abstract": "Abstract",
        "notes": "Notes",
        "slot_count": 1,
        "submission_type": submission_type,
        "additional_speaker": "",
    }
    response = client.post(current_url, data=info_data, follow=True)
    current_url = (
        response.redirect_chain[-1][0] if response.redirect_chain else current_url
    )
    user_data = {
        "register_name": "testuser@example.com",
        "register_email": "testuser@example.com",
        "register_password": "testpassw0rd!",
        "register_password_repeat": "testpassw0rd!",
    }
    response = client.post(current_url, data=user_data, follow=True)
    current_url = (
        response.redirect_chain[-1][0] if response.redirect_chain else current_url
    )
    profile_data = {
        "name": "Jane Doe",
        "biography": "Bio",
        "action": "draft",
    }
    response = client.post(current_url, data=profile_data, follow=True)
    access_code.refresh_from_db()
    assert (
        access_code.redeemed == 1
    ), "Access code should be redeemed when creating a draft"


@pytest.mark.django_db
def test_access_code_not_redeemed_again_on_dedraft(
    event,
    speaker,
    speaker_client,
    access_code,
    submission,
):
    event.cfp.deadline = now() - dt.timedelta(days=1)
    event.cfp.save()
    access_code.maximum_uses = 5
    access_code.redeemed = 1
    access_code.save()

    with scope(event=event):
        submission.access_code = access_code
        submission.state = "draft"
        submission.save()
        assert access_code.is_valid
        assert submission.editable

    data = {
        "action": "dedraft",
        "title": submission.title,
        "submission_type": submission.submission_type.pk,
        "content_locale": submission.content_locale,
        "description": submission.description or "",
        "abstract": "test",
        "notes": submission.notes or "",
        "resource-TOTAL_FORMS": 0,
        "resource-INITIAL_FORMS": 0,
        "resource-MIN_NUM_FORMS": 0,
        "resource-MAX_NUM_FORMS": 1000,
    }
    response = speaker_client.post(submission.urls.user_base, data=data)

    # redirect to cfp flow
    assert response.status_code == 302
    url = response.url
    response = speaker_client.get(url)

    # redirect to first cfp flow form
    assert response.status_code == 302
    url = response.url
    response = speaker_client.get(url)
    assert response.status_code == 200

    from bs4 import BeautifulSoup

    for _step in "info", "profile":
        soup = BeautifulSoup(response.render().content, "html.parser")
        form = soup.find_all("form")[1]
        form_data = {}
        for input_tag in form.find_all("input"):
            form_data[input_tag.get("name")] = input_tag.get("value", "")
        for input_tag in form.find_all("textarea"):
            form_data[input_tag.get("name")] = input_tag.text
        form_data["action"] = "submit"
        response = speaker_client.post(url, data=form_data)
        assert response.status_code == 302
        url = response.url
        response = speaker_client.get(url)
        assert response.status_code == 200

    access_code.refresh_from_db()
    assert (
        access_code.redeemed == 1
    ), "Access code should NOT be redeemed again when submitting a draft"

    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED
