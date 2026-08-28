# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.apps import apps
from django.template.defaultfilters import date as date_filter
from django.utils.functional import Promise
from django.utils.html import escape
from django.utils.timezone import localtime, now

from pretalx.common.log import (
    ACTION_LABELS,
    LOG_ALIASES,
    LOG_NAMES,
    _submission_label_text,
    action_type_label,
    compute_log_changes,
    default_activitylog_display,
    default_activitylog_object_link,
    generic_object_url,
    group_activity_log,
    resolve_log_changes,
)
from pretalx.common.models.log import ActivityLog
from pretalx.common.models.mixins import LogMixin
from pretalx.person.models import User
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    ActivityLogFactory,
    AnswerFactory,
    AnswerOptionFactory,
    AvailabilityFactory,
    EventFactory,
    MailTemplateFactory,
    QuestionFactory,
    QueuedMailFactory,
    ReviewFactory,
    RoomFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


def test_default_activitylog_display_known_action_type():
    log = ActivityLog(action_type="pretalx.submission.create")

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.submission.create"]


def test_default_activitylog_display_template_with_valid_data():
    log = ActivityLog(
        action_type="pretalx.event.delete",
        data={"name": "Test Event", "slug": "test", "organiser": "Org"},
    )

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == "The event Test Event (test) by Org was deleted."


def test_default_activitylog_display_template_with_missing_data():
    log = ActivityLog(action_type="pretalx.event.delete", data={"name": "Test Event"})

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.event.delete"]


def test_default_activitylog_display_template_with_non_dict_data():
    log = ActivityLog(action_type="pretalx.event.delete", data=None)

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES["pretalx.event.delete"]


@pytest.mark.parametrize(("alias", "resolved"), tuple(LOG_ALIASES.items()))
def test_default_activitylog_display_alias_resolves(alias, resolved):
    log = ActivityLog(action_type=alias)

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == LOG_NAMES[resolved]


def _log_prefixes_with_parent():
    return sorted(
        {
            model.log_prefix
            for model in apps.get_models()
            if getattr(model, "log_prefix", None)
            and model.log_parent is not LogMixin.log_parent
        }
    )


@pytest.mark.parametrize("prefix", _log_prefixes_with_parent())
def test_delete_actions_have_display_names(prefix):
    assert f"{prefix}.delete" in LOG_NAMES


def test_default_activitylog_display_unknown_action_type_returns_none():
    log = ActivityLog(action_type="pretalx.totally.unknown.action")

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result is None


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (SubmissionStates.ACCEPTED, "Session"),
        (SubmissionStates.CONFIRMED, "Session"),
        (SubmissionStates.SUBMITTED, "Proposal"),
        (SubmissionStates.REJECTED, "Proposal"),
        (SubmissionStates.CANCELED, "Proposal"),
        (SubmissionStates.WITHDRAWN, "Proposal"),
        (SubmissionStates.DRAFT, "Proposal"),
    ),
)
def test_submission_label_text_by_state(state, expected):
    submission = Submission(state=state)

    result = str(_submission_label_text(submission))

    assert result == expected


def test_group_activity_log_labels_day_buckets():
    logs = [
        ActivityLog(action_type="pretalx.event.update", timestamp=now()),
        ActivityLog(
            action_type="pretalx.event.update", timestamp=now() - dt.timedelta(days=1)
        ),
        ActivityLog(
            action_type="pretalx.event.update", timestamp=now() - dt.timedelta(days=400)
        ),
    ]

    groups = group_activity_log(logs, with_objects=False)

    old_day = localtime(logs[2].timestamp).date()
    assert [group["label"] for group in groups] == [
        "Today",
        "Yesterday",
        date_filter(old_day, "M j, Y"),
    ]
    assert all(len(group["entries"]) == 1 for group in groups)


def test_default_activitylog_object_link_no_content_object_returns_none():
    log = ActivityLog()

    result = default_activitylog_object_link(sender=None, activitylog=log)

    assert result is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "expected_label"),
    ((SubmissionStates.ACCEPTED, "Session"), (SubmissionStates.SUBMITTED, "Proposal")),
)
def test_default_activitylog_object_link_submission(state, expected_label):
    submission = SubmissionFactory(state=state)
    log = ActivityLog(content_object=submission)

    result = default_activitylog_object_link(sender=submission.event, activitylog=log)

    assert result == (
        f'{expected_label} <a href="{submission.orga_urls.base}">'
        f"{escape(submission.title)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_submission_comment():
    comment = SubmissionCommentFactory()
    log = ActivityLog(content_object=comment)

    result = default_activitylog_object_link(
        sender=comment.submission.event, activitylog=log
    )

    url = f"{comment.submission.orga_urls.comments}#comment-{comment.pk}"
    assert result == (
        f'Proposal <a href="{url}">{escape(comment.submission.title)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_review():
    review = ReviewFactory()
    log = ActivityLog(content_object=review)

    result = default_activitylog_object_link(
        sender=review.submission.event, activitylog=log
    )

    assert result == (
        f'Proposal <a href="{review.submission.orga_urls.reviews}">'
        f"{escape(review.submission.title)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_question():
    question = QuestionFactory()
    log = ActivityLog(content_object=question)

    result = default_activitylog_object_link(sender=question.event, activitylog=log)

    assert result == (
        f'Custom field <a href="{question.urls.base}">{escape(question.question)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_option():
    option = AnswerOptionFactory()
    log = ActivityLog(content_object=option)

    result = default_activitylog_object_link(
        sender=option.question.event, activitylog=log
    )

    assert result == (
        f'Custom field <a href="{option.question.urls.base}">'
        f"{escape(option.question.question)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_with_submission():
    answer = AnswerFactory()
    log = ActivityLog(content_object=answer)

    result = default_activitylog_object_link(
        sender=answer.question.event, activitylog=log
    )

    assert result == (
        f'Response to custom field <a href="{answer.submission.orga_urls.base}">'
        f"{escape(answer.question.question)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_answer_without_submission():
    answer = AnswerFactory(submission=None)
    log = ActivityLog(content_object=answer)

    result = default_activitylog_object_link(
        sender=answer.question.event, activitylog=log
    )

    assert result == (
        f'Response to custom field <a href="{answer.question.urls.base}">'
        f"{escape(answer.question.question)}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_cfp():
    event = EventFactory()
    cfp = event.cfp
    log = ActivityLog(content_object=cfp)

    result = default_activitylog_object_link(sender=event, activitylog=log)

    assert result == f'<a href="{cfp.urls.text}">Call for Proposals</a>'


@pytest.mark.django_db
def test_default_activitylog_object_link_mail_template():
    template = MailTemplateFactory()
    log = ActivityLog(content_object=template)

    result = default_activitylog_object_link(sender=template.event, activitylog=log)

    assert result == (
        f'Email template <a href="{template.urls.base}">{escape(template.subject)}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_queued_mail():
    mail = QueuedMailFactory()
    log = ActivityLog(content_object=mail)

    result = default_activitylog_object_link(sender=mail.event, activitylog=log)

    assert result == (f'Email <a href="{mail.urls.base}">{escape(mail.subject)}</a>')


@pytest.mark.django_db
def test_default_activitylog_object_link_speaker_profile():
    speaker = SpeakerFactory()
    log = ActivityLog(content_object=speaker)

    result = default_activitylog_object_link(sender=speaker.event, activitylog=log)

    assert result == (
        f'Speaker <a href="{speaker.orga_urls.base}">'
        f"{escape(speaker.user.get_display_name())}</a>"
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_managed_speaker_profile():
    speaker = SpeakerFactory(user=None, name="Managed Alice")
    log = ActivityLog(content_object=speaker)

    result = default_activitylog_object_link(sender=speaker.event, activitylog=log)

    assert result == f'Speaker <a href="{speaker.orga_urls.base}">Managed Alice</a>'


@pytest.mark.django_db
def test_default_activitylog_object_link_event():
    event = EventFactory()
    log = ActivityLog(content_object=event)

    result = default_activitylog_object_link(sender=event, activitylog=log)

    assert result == (
        f'Event <a href="{event.orga_urls.base}">{escape(str(event.name))}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_generic_fallback():
    track = TrackFactory()
    log = ActivityLog(content_object=track)

    result = default_activitylog_object_link(sender=track.event, activitylog=log)

    assert result == f'<a href="{track.urls.base}">{escape(str(track))}</a>'


@pytest.mark.django_db
def test_default_activitylog_object_link_generic_fallback_escapes_link_text():
    track = TrackFactory(name="<script>alert(1)</script>")
    log = ActivityLog(content_object=track)

    result = default_activitylog_object_link(sender=track.event, activitylog=log)

    assert result == (
        f'<a href="{track.urls.base}">&lt;script&gt;alert(1)&lt;/script&gt;</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_without_string_representation():
    information = SpeakerInformationFactory()
    log = ActivityLog(content_object=information)

    result = default_activitylog_object_link(sender=information.event, activitylog=log)

    assert result is None


@pytest.mark.django_db
def test_default_activitylog_object_link_without_urls():
    availability = AvailabilityFactory()
    log = ActivityLog(content_object=availability)

    result = default_activitylog_object_link(sender=availability.event, activitylog=log)

    assert result is None


def test_generic_object_url_of_none_is_empty():
    assert generic_object_url(None) == ""


@pytest.mark.django_db
def test_generic_object_url_prefers_the_organiser_url():
    event = EventFactory()

    assert generic_object_url(event) == event.orga_urls.base
    assert event.orga_urls.base != event.urls.base


@pytest.mark.django_db
def test_generic_object_url_falls_back_to_the_public_url():
    room = RoomFactory()

    assert not hasattr(room, "orga_urls")
    assert generic_object_url(room) == room.urls.base


@pytest.mark.parametrize(
    ("action_type", "expected"),
    (
        ("pretalx.submission.create", "Created"),
        ("pretalx.question.option.delete", "Option deleted"),
        ("pretalx.speaker.soft_delete", "Soft delete"),
        ("pretalx.submission.speakers.add", "Speakers add"),
        ("pretalx_pages.page.added", "Added"),
        ("weird", "Weird"),
        ("pretalx.submission.accept", "Accepted"),
        ("pretalx.submission.cancel", "Cancelled"),
        ("pretalx.submission.make_submitted", "Submitted"),
    ),
)
def test_action_type_label(action_type, expected):
    assert str(action_type_label(action_type)) == expected


@pytest.mark.parametrize("state", SubmissionStates.log_actions)
def test_action_labels_reuse_submission_state_labels(state):
    action = SubmissionStates.log_actions[state].removeprefix(".")

    assert ACTION_LABELS[action] is SubmissionStates(state).label


def test_action_type_label_stays_lazy():
    label = action_type_label("pretalx.submission.accept")

    assert isinstance(label, Promise)


def test_compute_log_changes_both_none():
    assert compute_log_changes(None, None) == {}


def test_compute_log_changes_identical_truthy_values():
    data = {"title": "Same Title", "state": "submitted"}

    assert compute_log_changes(data, data) == {}


def test_compute_log_changes_ignores_both_falsy():
    assert compute_log_changes({"key": ""}, {"key": None}) == {}


def test_compute_log_changes_mixed_keys():
    old_data = {"title": "Old Title", "state": "submitted", "track": None}
    new_data = {"title": "New Title", "state": "submitted", "track": 1}

    changes = compute_log_changes(old_data, new_data)

    assert changes["title"] == {"old": "Old Title", "new": "New Title"}
    assert "state" not in changes
    assert changes["track"] == {"old": None, "new": 1}


def test_compute_log_changes_tracks_additions():
    assert compute_log_changes({}, {"title": "New"}) == {
        "title": {"old": None, "new": "New"}
    }


def test_compute_log_changes_tracks_removals():
    assert compute_log_changes({"title": "Old"}, {}) == {
        "title": {"old": "Old", "new": None}
    }


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_without_data():
    log = ActivityLogFactory(data=None)

    assert resolve_log_changes(log) is None


@pytest.mark.django_db
def test_resolve_log_changes_without_event_resolves_content_object_fields():
    user = UserFactory()
    log = ActivityLogFactory(
        event=None,
        content_object=user,
        data={"changes": {"name": {"old": "A", "new": "B"}}},
    )
    name_field = User._meta.get_field("name")

    assert resolve_log_changes(log) == {
        "name": {
            "old": "A",
            "new": "B",
            "field": name_field,
            "label": name_field.verbose_name,
        }
    }


@pytest.mark.django_db
def test_resolve_log_changes_without_event_skips_question_lookup():
    question = QuestionFactory()
    user = UserFactory()
    log = ActivityLogFactory(
        event=None,
        content_object=user,
        data={"changes": {f"question-{question.pk}": {"old": "a", "new": "b"}}},
    )

    assert resolve_log_changes(log) == {
        f"question-{question.pk}": {"old": "a", "new": "b"}
    }


@pytest.mark.django_db
def test_resolve_log_changes_resolves_foreign_key_displays():
    submission = SubmissionFactory()
    old_track = TrackFactory(event=submission.event)
    new_track = TrackFactory(event=submission.event)
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"track": {"old": old_track.pk, "new": new_track.pk}}},
    )

    changes = resolve_log_changes(log)

    assert changes["track"]["old_display"] == str(old_track)
    assert changes["track"]["new_display"] == str(new_track)


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_without_changes_key():
    log = ActivityLogFactory(data={"some_key": "some_value"})

    assert resolve_log_changes(log) is None


@pytest.mark.django_db
def test_resolve_log_changes_labels_user_email():
    speaker = SpeakerFactory()
    log = ActivityLogFactory(
        content_object=speaker,
        event=speaker.event,
        action_type="pretalx.user.profile.update",
        data={
            "changes": {"user_email": {"old": "a@example.com", "new": "b@example.com"}}
        },
    )

    changes = resolve_log_changes(log)

    assert str(changes["user_email"]["label"]) == "Account email"


@pytest.mark.django_db
def test_resolve_log_changes_returns_none_when_content_object_deleted():
    submission = SubmissionFactory()
    log = ActivityLogFactory(
        content_object=submission,
        event=submission.event,
        data={"changes": {"title": {"old": "A", "new": "B"}}},
    )
    submission.delete()

    assert resolve_log_changes(log) is None


@pytest.mark.django_db
def test_group_activity_log_uses_event_speaker_name(django_assert_num_queries):
    user = UserFactory(name="Account Name")
    event = EventFactory()
    SpeakerFactory(user=user, event=event, name="Event Name")
    logs = list(
        ActivityLogFactory.create_batch(
            3, event=event, person=user, action_type="pretalx.event.update"
        )
    )

    with django_assert_num_queries(1):
        groups = group_activity_log(logs, with_objects=False)

    assert [
        entry["log"].person_display_name
        for group in groups
        for entry in group["entries"]
    ] == ["Event Name"] * 3


@pytest.mark.django_db
def test_group_activity_log_falls_back_to_account_name():
    user = UserFactory(name="Account Name")
    event = EventFactory()
    SpeakerFactory(user=user, event=event, name=None)
    log = ActivityLogFactory(
        event=event, person=user, action_type="pretalx.event.update"
    )

    group_activity_log([log], with_objects=False)

    assert log.person_display_name == "Account Name"


@pytest.mark.django_db
def test_activity_log_person_display_name_without_priming():
    user = UserFactory(name="Account Name")
    event = EventFactory()
    SpeakerFactory(user=user, event=event, name="Event Name")
    log = ActivityLogFactory(
        event=event, person=user, action_type="pretalx.event.update"
    )

    assert log.person_display_name == "Event Name"


@pytest.mark.django_db
def test_activity_log_person_display_name_without_person():
    assert ActivityLogFactory(person=None).person_display_name == ""
