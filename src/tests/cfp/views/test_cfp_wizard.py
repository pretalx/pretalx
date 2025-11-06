# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Michael Reichert

import datetime as dt
import json
from urllib.parse import urlparse

import bs4
import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http.request import QueryDict
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.submission.forms import InfoForm
from pretalx.submission.models import Submission, SubmissionStates, SubmissionType


class TestWizard:
    @staticmethod
    def get_response_and_url(client, url, follow=True, method="POST", data=None):
        if method == "GET":
            response = client.get(url, follow=follow, data=data)
        else:
            response = client.post(url, follow=follow, data=data)
        try:
            current_url = response.redirect_chain[-1][0]
        except IndexError:  # We are not being redirected at all!
            current_url = url
        return response, current_url

    def perform_init_wizard(self, client, success=True, event=None, access_code=None):
        # Start wizard
        djmail.outbox = []
        url = "/test/submit/"
        if access_code:
            url += f"?access_code={access_code.code}"
        response, current_url = self.get_response_and_url(client, url, method="GET")
        assert ("/info/" in current_url) is success
        return response, current_url

    def perform_info_wizard(
        self,
        client,
        response,
        url,
        next_step="questions",
        title="Submission title",
        content_locale="en",
        description="Description",
        abstract="Abstract",
        notes="Notes",
        slot_count=1,
        submission_type=None,
        event=None,
        track=None,
        additional_speaker=None,
    ):
        submission_data = {
            "title": title,
            "content_locale": content_locale,
            "description": description,
            "abstract": abstract,
            "notes": notes,
            "slot_count": slot_count,
            "submission_type": submission_type,
            "additional_speaker": additional_speaker or "",
        }
        if track:
            submission_data["track"] = getattr(track, "pk", track)
        response, current_url = self.get_response_and_url(
            client, url, data=submission_data
        )
        assert (
            f"/{next_step}/" in current_url
        ), f"{current_url} does not end with /{next_step}/!"
        return response, current_url

    def perform_question_wizard(
        self, client, response, url, data, next_step="profile", event=None
    ):
        response, current_url = self.get_response_and_url(client, url, data=data)
        assert (
            f"/{next_step}/" in current_url
        ), f"{current_url} does not end with /{next_step}/!"
        return response, current_url

    def perform_user_wizard(
        self,
        client,
        response,
        url,
        password,
        next_step="profile",
        email=None,
        register=False,
        event=None,
    ):
        if register:
            data = {
                "register_name": email,
                "register_email": email,
                "register_password": password,
                "register_password_repeat": password,
            }
        else:
            data = {"login_email": email, "login_password": password}
        response, current_url = self.get_response_and_url(client, url, data=data)
        assert (
            f"/{next_step}/" in current_url
        ), f"{current_url} does not end with /{next_step}/!"
        return response, current_url

    def perform_profile_form(
        self,
        client,
        response,
        url,
        name="Jane Doe",
        bio="l337 hax0r",
        next_step="me/submissions",
        event=None,
        success=True,
    ):
        data = {"name": name, "biography": bio}
        response, current_url = self.get_response_and_url(client, url, data=data)
        assert (
            f"/{next_step}/" in current_url
        ), f"{current_url} does not end with /{next_step}/!"
        doc = bs4.BeautifulSoup(response.rendered_content, "lxml")
        assert bool(doc.select(".alert-success")) is success
        assert bool(doc.select("#user-dropdown-label")) is success
        return response, current_url

    def assert_submission(
        self,
        event,
        title="Submission title",
        content_locale="en",
        description="Description",
        abstract="Abstract",
        notes="Notes",
        question=None,
        answer="42",
        track=None,
    ):
        with scope(event=event):
            sub = Submission.objects.last()
            assert sub.title == title
            assert sub.submission_type is not None
            assert sub.content_locale == content_locale
            assert sub.description == description
            assert sub.abstract == abstract
            assert sub.notes == notes
            assert sub.slot_count == 1
            if question:
                answ = sub.answers.first()
                assert answ
                assert answ.question == question
                assert answ.answer == answer
            else:
                assert sub.answers.count() == 0
            if track:
                assert sub.track == track
            else:
                assert sub.track is None
        return sub

    def assert_user(
        self,
        submission,
        email="testuser@example.com",
        name="Jane Doe",
        biography="l337 hax0r",
        question=None,
        answer=None,
    ):
        with scope(event=submission.event):
            user = submission.speakers.get(email=email)
            assert user.name == name
            assert user.profiles.get(event=submission.event).biography == biography
            if question:
                answ = user.answers.filter(question__target="speaker").first()
                assert answ
                assert answ.question == question
                assert answ.person == user
                assert not answ.submission
                assert answ.answer == "green"
        return user

    def assert_mail(self, submission, user, count=1, extra=None):
        assert len(djmail.outbox) == count
        mail = djmail.outbox[0 if not extra else 1]
        assert submission.title in mail.subject
        assert submission.title in mail.body
        assert user.email in mail.to
        if extra:
            assert djmail.outbox[0].to == [extra]

    @pytest.mark.django_db
    def test_info_wizard_query_string_handling(self, event, client, track):
        # build query string
        params_dict = QueryDict(f"track={track.pk}&submission_type=academic_talk")
        current_url = "/test/submit/?{params_dict}"
        # Start wizard
        _, current_url = self.get_response_and_url(client, current_url, method="GET")
        # get query string from current URL
        url_parts = urlparse(current_url)
        q = QueryDict(url_parts.query)
        assert url_parts.path.endswith("/info/") is True
        assert q.get("track") == params_dict.get("academic")
        assert q.get("submission_type") == params_dict.get("academic_talk")

    @pytest.mark.django_db
    def test_wizard_new_user(self, event, question, client):
        event.mail_settings["mail_on_new_submission"] = True
        event.plugins = "tests"
        event.save()
        event.settings.submission_state_change_called = ""
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first()
            submission_type.deadline = event.cfp.deadline
            submission_type.save()
            event.deadline = now() - dt.timedelta(days=1)
            event.locale_array = "de,en"
            event.save()
            submission_type = submission_type.pk
        answer_data = {f"question_{question.pk}": "42"}

        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url + f"?submission_type={submission_type}-helpful-slug",
            submission_type=submission_type,
            event=event,
        )
        response, current_url = self.perform_question_wizard(
            client, response, current_url, answer_data, next_step="user", event=event
        )
        # Try to login first, then remember you don't have an account yet
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            email="wrong@example.org",
            password="testpassw0rd!",
            event=event,
            next_step="user",
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            password="testpassw0rd!",
            email="testuser@example.com",
            register=True,
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event, question=question)
        self.assert_user(submission, email="testuser@example.com")
        assert len(djmail.outbox) == 2  # user email plus orga email
        assert (
            submission.event.settings.submission_state_change_called == submission.code
        )

    @pytest.mark.django_db
    def test_wizard_existing_user(
        self,
        event,
        client,
        question,
        user,
        speaker_question,
        choice_question,
        multiple_choice_question,
        file_question,
    ):
        with scope(event=event):
            event.cfp.deadline = now() + dt.timedelta(days=1)
            event.save()
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            answer_data = {
                f"question_{question.pk}": "42",
                f"question_{speaker_question.pk}": "green",
                f"question_{choice_question.pk}": choice_question.options.first().pk,
                f"question_{multiple_choice_question.pk}": multiple_choice_question.options.first().pk,
                f"question_{file_question.pk}": SimpleUploadedFile(
                    "testfile.txt", b"file_content"
                ),
            }

        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url + "?submission_type=123-helpful-slug",
            submission_type=submission_type,
            event=event,
        )
        response, current_url = self.perform_question_wizard(
            client,
            response,
            current_url,
            answer_data,
            next_step="user",
            event=event,
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            email=user.email,
            password="testpassw0rd!",
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )

        submission = self.assert_submission(event, question=question)
        user = self.assert_user(submission, question=speaker_question, answer="green")
        self.assert_mail(submission, user)
        with scope(event=event):
            assert file_question.answers.first().answer_file.read() == b"file_content"

    @pytest.mark.django_db
    def test_wizard_logged_in_user(
        self, event, client, question, user, review_question
    ):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            answer_data = {f"question_{question.pk}": "42"}

        client.force_login(user)
        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            event=event,
        )
        response, current_url = self.perform_question_wizard(
            client,
            response,
            current_url,
            answer_data,
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event, question=question)
        user = self.assert_user(submission)
        self.assert_mail(submission, user)

    @pytest.mark.django_db
    def test_wizard_logged_in_user_no_questions(self, event, client, user):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk

        client.force_login(user)
        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="profile",
            event=event,
            additional_speaker="additional@example.com",
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event)
        user = self.assert_user(submission)
        self.assert_mail(submission, user, extra="additional@example.com", count=2)

    @pytest.mark.django_db
    def test_wizard_logged_in_user_additional_speaker_mail_fail(
        self, event, client, user
    ):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            event.mail_settings["smtp_use_custom"] = True
            event.save()

        client.force_login(user)
        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="profile",
            event=event,
            additional_speaker="additional@example.com",
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event)
        user = self.assert_user(submission)
        assert len(djmail.outbox) == 0

    @pytest.mark.django_db
    def test_wizard_logged_in_user_only_review_questions(
        self, event, client, user, review_question
    ):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk

        client.force_login(user)
        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="profile",
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event)
        user = self.assert_user(submission)
        self.assert_mail(submission, user)

    @pytest.mark.django_db
    def test_wizard_logged_in_user_no_questions_broken_template(
        self, event, client, user
    ):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            ack_template = event.get_mail_template("submission.new")
            ack_template.text = str(ack_template.text) + "{name} and {nonexistent}"
            ack_template.save()

        client.force_login(user)
        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="profile",
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event)
        user = self.assert_user(submission)
        assert len(djmail.outbox) == 0

    @pytest.mark.django_db
    def test_wizard_with_tracks(self, event, client, track, other_track):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            event.cfp.fields["track"]["visibility"] = "required"
            event.cfp.save()

        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="user",
            event=event,
            track=track,
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            password="testpassw0rd!",
            email="testuser@example.com",
            register=True,
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event, track=track)
        user = self.assert_user(submission, email="testuser@example.com")
        self.assert_mail(submission, user)

    @pytest.mark.django_db
    def test_wizard_cfp_closed_after_deadline(self, event, client, user):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
        client.force_login(user)
        self.perform_init_wizard(client, success=False, event=event)

    @pytest.mark.django_db
    def test_wizard_cfp_closed_before_opening(self, event, client, user):
        event.cfp.opening = now() + dt.timedelta(days=1)
        event.cfp.save()
        client.force_login(user)
        self.perform_init_wizard(client, success=False, event=event)

    @pytest.mark.django_db
    def test_wizard_cfp_closed_access_code(self, event, client, access_code):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
        response, current_url = self.perform_init_wizard(
            client, event=event, access_code=access_code
        )
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            event=event,
            next_step="user",
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            password="testpassw0rd!",
            email="testuser@example.com",
            register=True,
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        submission = self.assert_submission(event)
        assert submission.access_code == access_code

    @pytest.mark.django_db
    def test_wizard_cfp_closed_expired_access_code(self, event, client, access_code):
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()
        access_code.valid_until = now() - dt.timedelta(hours=1)
        access_code.save()
        response, _ = self.perform_init_wizard(
            client, event=event, access_code=access_code, success=False
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_wizard_track_access_code_and_question(
        self,
        event,
        client,
        access_code,
        track,
        other_track,
        question,
    ):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            event.cfp.fields["track"]["visibility"] = "required"
            event.cfp.fields["abstract"]["visibility"] = "do_not_ask"
            event.cfp.save()
            track.requires_access_code = True
            track.save()
            question.tracks.add(track)
            other_track.requires_access_code = True
            other_track.save()
            access_code.track = track
            access_code.submission_type = event.cfp.default_type
            access_code.save()

        response, current_url = self.perform_init_wizard(client, event=event)
        self.perform_info_wizard(  # Does not work without token
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="info",
            event=event,
            track=track,
        )
        (
            response,
            current_url,
        ) = self.perform_info_wizard(  # Works with token and right track
            client,
            response,
            current_url + "?access_code=" + access_code.code,
            submission_type=submission_type,
            next_step="questions",
            event=event,
            track=track,
        )
        answer_data = {f"question_{question.pk}": 42}
        response, current_url = self.perform_question_wizard(
            client, response, current_url, answer_data, next_step="user", event=event
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            password="testpassw0rd!",
            email="testuser@example.com",
            register=True,
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        self.assert_submission(event, track=track, question=question, abstract=None)

    @pytest.mark.django_db
    def test_wizard_submission_type_access_code(self, event, client, access_code):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first()
            submission_type.requires_access_code = True
            submission_type.save()
            submission_type = submission_type.pk

        response, current_url = self.perform_init_wizard(client, event=event)
        (
            response,
            current_url,
        ) = self.perform_info_wizard(  # Does not work without access token
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="info",
            event=event,
        )
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url + "?access_code=" + access_code.code,
            submission_type=submission_type,
            next_step="user",
            event=event,
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            password="testpassw0rd!",
            email="testuser@example.com",
            register=True,
            event=event,
        )
        response, current_url = self.perform_profile_form(
            client, response, current_url, event=event
        )
        self.assert_submission(event)

    @pytest.mark.django_db
    def test_wizard_request_missing_step(self, event, client):
        _, current_url = self.perform_init_wizard(client, event=event)
        response = client.get(current_url.replace("info", "wrooooong"))
        assert response.status_code == 404

    @pytest.mark.django_db
    def test_wizard_existing_user_twice(
        self,
        event,
        client,
        user,
        speaker_question,
    ):
        with scope(event=event):
            assert event.submissions.count() == 0
            assert speaker_question.answers.count() == 0
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            answer_data = {f"question_{speaker_question.pk}": "green"}

        client.force_login(user)
        for _ in range(2):
            response, current_url = self.perform_init_wizard(client, event=event)
            response, current_url = self.perform_info_wizard(
                client,
                response,
                current_url,
                submission_type=submission_type,
                event=event,
            )
            response, current_url = self.perform_question_wizard(
                client,
                response,
                current_url,
                answer_data,
                event=event,
            )
            response, current_url = self.perform_profile_form(
                client, response, current_url, event=event
            )
            submission = self.assert_submission(event)
            self.assert_user(submission, question=speaker_question, answer="green")
        with scope(event=event):
            assert event.submissions.count() == 2
            assert speaker_question.answers.count() == 1

    @pytest.mark.django_db
    def test_wizard_with_availabilities(self, event, client):
        """Test that submitting with availabilities doesn't return None."""

        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            event.cfp.fields["availabilities"]["visibility"] = "required"
            event.cfp.save()

        response, current_url = self.perform_init_wizard(client, event=event)
        response, current_url = self.perform_info_wizard(
            client,
            response,
            current_url,
            submission_type=submission_type,
            next_step="user",
            event=event,
        )
        response, current_url = self.perform_user_wizard(
            client,
            response,
            current_url,
            password="testpassw0rd!",
            email="testuser@example.com",
            register=True,
            event=event,
        )

        # Submit profile with availabilities
        avail_data = {
            "availabilities": [
                {
                    "start": f"{event.date_from}T10:00:00.000Z",
                    "end": f"{event.date_from}T18:00:00.000Z",
                }
            ],
            "event": {
                "timezone": str(event.timezone),
                "date_from": str(event.date_from),
                "date_to": str(event.date_to),
            },
        }
        data = {
            "name": "Jane Doe",
            "biography": "l337 hax0r",
            "availabilities": json.dumps(avail_data),
        }
        response, current_url = self.get_response_and_url(
            client, current_url, data=data
        )

        # This should redirect to submissions page, not return None
        assert response.status_code == 200
        assert "/me/submissions/" in current_url

        submission = self.assert_submission(event)
        user = self.assert_user(submission, email="testuser@example.com")
        self.assert_mail(submission, user)


@pytest.mark.django_db
def test_infoform_set_submission_type(event, other_event):
    # https://github.com/pretalx/pretalx/issues/642
    with scopes_disabled():
        assert len(SubmissionType.objects.all()) > 1
    with scope(event=event):
        f = InfoForm(event)
        assert len(event.submission_types.all()) == 1
        assert "submission_type" not in f.fields
        assert f.initial["submission_type"] == event.submission_types.first()
        assert "submission_type" not in f.fields


@pytest.mark.django_db
def test_infoform_set_submission_type_2nd_event(event, other_event, submission_type):
    # https://github.com/pretalx/pretalx/issues/642
    with scopes_disabled():
        assert len(SubmissionType.objects.all()) > 1
    with scope(event=event):
        f = InfoForm(event)
        assert len(event.submission_types.all()) == 2
        assert len(f.fields["submission_type"].queryset) == 2


class TestWizardDrafts:

    @pytest.mark.django_db
    def test_draft_not_saved_with_invalid_data_on_info_step(self, event, client):
        """Test that clicking 'save as draft' with invalid form data doesn't create a draft.

        After the fix: When the user clicks 'save as draft' with invalid form data,
        they stay on the same page with validation errors shown, and no confusing
        redirect happens.
        """
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            initial_submission_count = Submission.all_objects.count()

        response = client.get("/test/submit/", follow=True)
        current_url = response.redirect_chain[-1][0]
        assert "/info/" in current_url

        # Missing required field: title
        invalid_data = {
            "action": "draft",
            "content_locale": "en",
            "description": "Some description",
            "abstract": "Some abstract",
            "notes": "Some notes",
            "slot_count": 1,
            "submission_type": submission_type,
        }
        response = client.post(current_url, data=invalid_data, follow=True)

        final_url = (
            response.redirect_chain[-1][0] if response.redirect_chain else current_url
        )
        assert "/info/" in final_url
        assert "draft=1" not in final_url

        with scope(event=event):
            assert Submission.all_objects.count() == initial_submission_count
            assert (
                Submission.all_objects.filter(state=SubmissionStates.DRAFT).count() == 0
            )

        doc = bs4.BeautifulSoup(response.content, "html.parser")
        errors = doc.select(".alert-danger, .errorlist")
        assert len(errors) > 0, "Validation errors should be displayed"

    @pytest.mark.django_db
    def test_draft_not_saved_with_invalid_data_on_profile_step(self, event, client):
        """Test that clicking 'save as draft' with invalid profile data doesn't create a draft."""
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            initial_submission_count = Submission.all_objects.count()

        response = client.get("/test/submit/", follow=True)
        current_url = response.redirect_chain[-1][0]

        info_data = {
            "title": "Test Submission",
            "content_locale": "en",
            "description": "Description",
            "abstract": "Abstract",
            "notes": "Notes",
            "slot_count": 1,
            "submission_type": submission_type,
        }
        response = client.post(current_url, data=info_data, follow=True)
        current_url = response.redirect_chain[-1][0]

        user_data = {
            "register_name": "testuser@example.com",
            "register_email": "testuser@example.com",
            "register_password": "testpassw0rd!",
            "register_password_repeat": "testpassw0rd!",
        }
        response = client.post(current_url, data=user_data, follow=True)
        current_url = response.redirect_chain[-1][0]

        invalid_profile_data = {
            "action": "draft",
            "biography": "Bio",
        }
        response = client.post(current_url, data=invalid_profile_data, follow=True)

        final_url = (
            response.redirect_chain[-1][0] if response.redirect_chain else current_url
        )
        assert "/profile/" in final_url
        assert "draft=1" not in final_url

        with scope(event=event):
            assert Submission.all_objects.count() == initial_submission_count
            assert (
                Submission.all_objects.filter(state=SubmissionStates.DRAFT).count() == 0
            )

        doc = bs4.BeautifulSoup(response.content, "html.parser")
        errors = doc.select(".alert-danger, .errorlist")
        assert len(errors) > 0, "Validation errors should be displayed"

    @pytest.mark.django_db
    def test_draft_saved_successfully_with_valid_data(self, event, client, user):
        with scope(event=event):
            submission_type = SubmissionType.objects.filter(event=event).first().pk
            initial_submission_count = Submission.all_objects.count()

        response = client.get("/test/submit/", follow=True)
        current_url = response.redirect_chain[-1][0]
        assert "/info/" in current_url

        valid_data = {
            "action": "draft",
            "title": "Draft Submission",
            "content_locale": "en",
            "description": "Draft description",
            "abstract": "Draft abstract",
            "notes": "Draft notes",
            "slot_count": 1,
            "submission_type": submission_type,
        }
        response = client.post(current_url, data=valid_data, follow=True)

        # No draft should be created yet (user needs to login first)
        final_url = (
            response.redirect_chain[-1][0] if response.redirect_chain else current_url
        )
        assert "/user/" in final_url
        assert "draft=1" in final_url
        with scope(event=event):
            assert Submission.all_objects.count() == initial_submission_count
        user_data = {
            "login_email": user.email,
            "login_password": "testpassw0rd!",
        }
        response = client.post(final_url, data=user_data, follow=True)

        # After login, should redirect to /me/submissions/
        final_url = (
            response.redirect_chain[-1][0] if response.redirect_chain else final_url
        )
        assert "/me/submissions/" in final_url

        with scope(event=event):
            assert Submission.all_objects.count() == initial_submission_count + 1
            draft = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
            assert draft is not None
            assert draft.title == "Draft Submission"
            assert draft.description == "Draft description"
            assert draft.abstract == "Draft abstract"
            assert draft.notes == "Draft notes"

        assert "Draft Submission" in response.content.decode()
