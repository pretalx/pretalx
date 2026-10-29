# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.interfaces.forms import WriteSessionMailForm
from pretalx.orga.views.mails import (
    ComposeSessionMail,
    MailDelete,
    MailDetail,
    MailTemplateView,
    OutboxList,
    OutboxSend,
    SentMail,
)
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view, query_dict

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_outbox_and_sent_list_split_by_state(event):
    draft = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    sent = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    outbox = make_view(OutboxList, request)
    outbox.object_list = []

    assert list(outbox.get_queryset()) == [draft]
    assert list(make_view(SentMail, request).get_queryset()) == [sent]
    kwargs = outbox.get_table_kwargs()
    assert kwargs["has_update_permission"] is True
    assert kwargs["has_delete_permission"] is True


@pytest.mark.parametrize("view_class", (OutboxList, SentMail))
@pytest.mark.parametrize(
    ("feature_flag", "create_track", "expected"),
    ((True, True, True), (True, False, False), (False, True, False)),
)
def test_show_tracks_reflects_active_tracks(
    view_class, feature_flag, create_track, expected
):
    event = EventFactory(feature_flags={"use_tracks": feature_flag})
    if create_track:
        TrackFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(view_class, request)

    assert view.show_tracks is expected


def test_outbox_send_queryset_filters_by_pks_and_failure(event):
    failed = QueuedMailFactory(
        event=event, state=QueuedMailStates.DRAFT, error_data={"error": "fail"}
    )
    QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)

    def send_view(params):
        request = make_request(event, user=user)
        request.GET = query_dict(params)
        return make_view(OutboxSend, request)

    assert list(send_view({"pks": str(failed.pk)}).queryset) == [failed]
    assert list(send_view({"pks": ",,,,,"}).queryset) == []
    assert list(send_view({"failed_only": "1"}).queryset) == [failed]


def test_mail_delete_queryset_single_or_all_by_template(event):
    template = MailTemplateFactory(event=event)
    mail1 = QueuedMailFactory(
        event=event, state=QueuedMailStates.DRAFT, template=template
    )
    mail2 = QueuedMailFactory(
        event=event, state=QueuedMailStates.DRAFT, template=template
    )
    QueuedMailFactory(event=event, state=QueuedMailStates.SENT, template=template)
    user = make_orga_user(event, can_change_submissions=True)
    single_request = make_request(event, user=user)
    single_request.GET = query_dict()
    all_request = make_request(event, user=user)
    all_request.GET = query_dict({"all": "true"})

    assert list(make_view(MailDelete, single_request, pk=mail1.pk).queryset) == [mail1]
    assert set(make_view(MailDelete, all_request, pk=mail1.pk).queryset) == {
        mail1,
        mail2,
    }


def test_mail_detail_get_object(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)

    assert make_view(MailDetail, request, pk=mail.pk).get_object() == mail
    assert make_view(MailDetail, request, pk=99999).get_object() is None


def test_mail_detail_get_context_data(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    log = ActivityLogFactory(event=event, content_object=mail)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailDetail, request, pk=mail.pk)
    view.object = mail
    view_only = make_view(MailDetail, request, pk=mail.pk)
    view_only.object = mail
    # Force view-only permission to exercise the defensive branch
    view_only.__dict__["permission_action"] = "view"

    ctx = view.get_context_data()
    view_only_ctx = view_only.get_context_data()

    assert ctx["history_log_entries"] == [log]
    assert list(ctx["tablist"].keys()) == ["email", "history"]
    assert "submit_buttons" in ctx
    assert "submit_buttons" not in view_only_ctx
    assert "submit_buttons_extra" not in view_only_ctx


def test_compose_session_mail_get_form_kwargs_from_query(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    by_submission = make_request(event, user=user)
    by_submission.GET = query_dict({"submissions": submission.code})
    by_speaker = make_request(event, user=user)
    by_speaker.GET = query_dict({"speakers": speaker.code})

    submission_kwargs = make_view(ComposeSessionMail, by_submission).get_form_kwargs()
    speaker_kwargs = make_view(ComposeSessionMail, by_speaker).get_form_kwargs()

    assert submission_kwargs["initial"]["submissions"] == [submission.code]
    assert list(speaker_kwargs["initial"]["speakers"]) == [speaker]


def test_compose_session_mail_get_recipient_count_counts_unique_contexts(event):
    speaker = SpeakerFactory(event=event)
    sub_a = SubmissionFactory(event=event)
    sub_b = SubmissionFactory(event=event)
    sub_a.speakers.add(speaker)
    sub_b.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ComposeSessionMail, request)
    form = WriteSessionMailForm(
        event=event,
        data={"submissions": [sub_a.code, sub_b.code], "subject_0": "x", "text_0": "y"},
    )
    assert form.is_valid(), form.errors

    # One speaker, two submissions: two distinct recipient contexts. This
    # mirrors the preview estimate, not the task-level subject/text dedup.
    assert view.get_recipient_count(form) == 2


def test_mail_template_view_get_queryset_excludes_auto_created(event):
    custom = MailTemplateFactory(event=event)
    auto_created = MailTemplateFactory(event=event, is_auto_created=True)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailTemplateView, request)
    view.action = "list"

    result = list(view.get_queryset())

    assert custom in result
    assert auto_created not in result
