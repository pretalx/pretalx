# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import io

import pytest
from django.apps import apps
from django.core.files import File
from django.core.files.base import ContentFile
from django.template.defaultfilters import date as date_filter
from django.utils import translation
from django.utils.functional import Promise
from django.utils.html import escape
from django.utils.timezone import localtime, now
from i18nfield.strings import LazyI18nString

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
    log_settings_changes,
    resolve_log_changes,
    serialize_setting_value,
    settings_fields,
    settings_snapshot,
)
from pretalx.common.models.log import ActivityLog
from pretalx.common.models.mixins import LogMixin
from pretalx.mail.interfaces.forms.config import MailSettingsForm
from pretalx.orga.forms.cfp import CfPSettingsForm
from pretalx.person.models import User
from pretalx.submission.interfaces.forms.review import ReviewSettingsForm
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


@pytest.mark.parametrize(
    ("action_type", "data", "expected"),
    (
        ("pretalx.submission.create", None, LOG_NAMES["pretalx.submission.create"]),
        (
            "pretalx.event.delete",
            {"name": "Test Event", "slug": "test", "organiser": "Org"},
            "The event Test Event (test) by Org was deleted.",
        ),
        (
            "pretalx.event.delete",
            {"name": "Test Event"},
            LOG_NAMES["pretalx.event.delete"],
        ),
        ("pretalx.event.delete", None, LOG_NAMES["pretalx.event.delete"]),
        ("pretalx.totally.unknown.action", None, None),
    ),
    ids=("known", "template", "template_missing_data", "template_no_data", "unknown"),
)
def test_default_activitylog_display(action_type, data, expected):
    log = ActivityLog(action_type=action_type, data=data)

    result = default_activitylog_display(sender=None, activitylog=log)

    assert result == expected


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
def test_default_activitylog_object_link_question_option_and_answers():
    option = AnswerOptionFactory()
    question = option.question
    event = question.event
    answer = AnswerFactory(question=question)
    orphan_answer = AnswerFactory(question=question, submission=None)
    question_link = (
        f'Custom field <a href="{question.urls.base}">{escape(question.question)}</a>'
    )

    def link(obj):
        return default_activitylog_object_link(
            sender=event, activitylog=ActivityLog(content_object=obj)
        )

    assert link(question) == question_link
    assert link(option) == question_link
    assert link(answer) == (
        f'Response to custom field <a href="{answer.submission.orga_urls.base}">'
        f"{escape(question.question)}</a>"
    )
    assert link(orphan_answer) == (
        f'Response to custom field <a href="{question.urls.base}">'
        f"{escape(question.question)}</a>"
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
    managed = SpeakerFactory(event=speaker.event, user=None, name="Managed Alice")

    def link(obj):
        return default_activitylog_object_link(
            sender=speaker.event, activitylog=ActivityLog(content_object=obj)
        )

    assert link(speaker) == (
        f'Speaker <a href="{speaker.orga_urls.base}">'
        f"{escape(speaker.user.get_display_name())}</a>"
    )
    assert (
        link(managed) == f'Speaker <a href="{managed.orga_urls.base}">Managed Alice</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_event():
    event = EventFactory()
    log = ActivityLog(content_object=event)

    result = default_activitylog_object_link(sender=event, activitylog=log)

    assert result == (
        f'Event <a href="{event.orga_urls.base}">{escape(str(event.name))}</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_generic_fallback_escapes_link_text():
    track = TrackFactory(name="<script>alert(1)</script>")
    log = ActivityLog(content_object=track)

    result = default_activitylog_object_link(sender=track.event, activitylog=log)

    assert result == (
        f'<a href="{track.urls.base}">&lt;script&gt;alert(1)&lt;/script&gt;</a>'
    )


@pytest.mark.django_db
def test_default_activitylog_object_link_without_urls_or_string_representation():
    information = SpeakerInformationFactory()
    availability = AvailabilityFactory(event=information.event)

    for obj in (information, availability):
        log = ActivityLog(content_object=obj)
        assert (
            default_activitylog_object_link(sender=information.event, activitylog=log)
            is None
        )


@pytest.mark.django_db
def test_generic_object_url_prefers_the_organiser_url():
    event = EventFactory()
    room = RoomFactory(event=event)

    assert generic_object_url(None) == ""
    assert generic_object_url(event) == event.orga_urls.base
    assert event.orga_urls.base != event.urls.base
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
    assert isinstance(action_type_label(f"pretalx.submission.{action}"), Promise)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    (
        (None, None, {}),
        (
            {"title": "Same Title", "state": "submitted"},
            {"title": "Same Title", "state": "submitted"},
            {},
        ),
        ({"key": ""}, {"key": None}, {}),
        (
            {"title": "Old Title", "state": "submitted", "track": None},
            {"title": "New Title", "state": "submitted", "track": 1},
            {
                "title": {"old": "Old Title", "new": "New Title"},
                "track": {"old": None, "new": 1},
            },
        ),
        ({}, {"title": "New"}, {"title": {"old": None, "new": "New"}}),
        ({"title": "Old"}, {}, {"title": {"old": "Old", "new": None}}),
        ({"name": "DemoCon"}, {"name": {"en": "DemoCon"}}, {}),
        ({"name": {"de": "DemoCon"}}, {"name": "DemoCon"}, {}),
        (
            {"name": "DemoCon"},
            {"name": {"en": "DemoCon", "de": "DemoCon"}},
            {"name": {"old": "DemoCon", "new": {"en": "DemoCon", "de": "DemoCon"}}},
        ),
        (
            {"name": "DemoCon"},
            {"name": {"en": "Other"}},
            {"name": {"old": "DemoCon", "new": {"en": "Other"}}},
        ),
    ),
    ids=(
        "both_none",
        "identical",
        "both_falsy",
        "mixed_keys",
        "addition",
        "removal",
        "locale-dict-new",
        "locale-dict-old",
        "two-locales",
        "different-text",
    ),
)
def test_compute_log_changes(old, new, expected):
    assert compute_log_changes(old, new) == expected


def test_compute_log_changes_orders_new_data_first():
    old_data = {"echo": "old", "alpha": "old", "foxtrot": "old"}
    new_data = {"delta": "new", "bravo": "new", "charlie": "new", "alpha": "new"}

    changes = compute_log_changes(old_data, new_data)

    assert list(changes) == ["delta", "bravo", "charlie", "alpha", "echo", "foxtrot"]


@pytest.mark.django_db
@pytest.mark.parametrize("data", (None, {"some_key": "some_value"}))
def test_resolve_log_changes_returns_none_without_changes(data):
    log = ActivityLogFactory(data=data)

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
    unnamed = UserFactory(name="Other Account")
    event = EventFactory()
    SpeakerFactory(user=user, event=event, name="Event Name")
    SpeakerFactory(user=unnamed, event=event, name=None)
    logs = list(
        ActivityLogFactory.create_batch(
            3, event=event, person=user, action_type="pretalx.event.update"
        )
    ) + [
        ActivityLogFactory(
            event=event, person=unnamed, action_type="pretalx.event.update"
        ),
        ActivityLogFactory(
            event=event, person=None, action_type="pretalx.event.update"
        ),
    ]

    with django_assert_num_queries(1):
        groups = group_activity_log(logs, with_objects=False)

    assert [
        entry["log"].person_display_name
        for group in groups
        for entry in group["entries"]
    ] == ["Event Name"] * 3 + ["Other Account", ""]


@pytest.mark.django_db
def test_activity_log_person_display_name_without_priming():
    user = UserFactory(name="Account Name")
    event = EventFactory()
    SpeakerFactory(user=user, event=event, name="Event Name")
    log = ActivityLogFactory(
        event=event, person=user, action_type="pretalx.event.update"
    )

    assert log.person_display_name == "Event Name"


def test_settings_fields_maps_json_columns_and_hierarkey_settings():
    fields = settings_fields(ReviewSettingsForm)

    assert (
        fields["feature_flags.use_submission_comments"]
        is ReviewSettingsForm.base_fields["use_submission_comments"]
    )
    assert (
        fields["settings.review_help_text"]
        is ReviewSettingsForm.base_fields["review_help_text"]
    )


def test_serialize_setting_value_of_file():
    value = File(io.BytesIO(b"png"), name="pub/logo.png")

    assert serialize_setting_value(value, ["en"]) == "pub/logo.png"


@pytest.mark.django_db
def test_settings_snapshot_expands_settings_into_dotted_keys():
    event = EventFactory()
    event.feature_flags["use_submission_comments"] = True
    event.custom_css.save("custom.css", ContentFile(b"body { color: red }"))
    event.save()
    event.settings.set("review_help_text", LazyI18nString({"en": "Be nice"}))

    data = settings_snapshot(event, ReviewSettingsForm)

    assert data["feature_flags.use_submission_comments"] is True
    assert data["review_settings.score_mandatory"] is False
    assert data["settings.review_help_text"] == {"en": "Be nice"}
    assert "use_submission_comments" not in data["feature_flags"]
    assert data["feature_flags"]["use_tracks"] is True
    assert data["review_settings"] == {}
    assert data["custom_css"] == event.custom_css.name


@pytest.mark.django_db
def test_log_settings_changes_diffs_custom_css_content():
    event = EventFactory()

    with log_settings_changes(event, "pretalx.event.update", person=UserFactory()):
        event.custom_css.save("custom.css", ContentFile(b"body { color: red }"))

    log = event.logged_actions().get()
    assert log.data["changes"]["custom_css"] == {
        "old": "",
        "new": "body { color: red }",
    }


@pytest.mark.django_db
def test_log_settings_changes_with_missing_css_file_logs_name():
    event = EventFactory()
    event.custom_css.save("custom.css", ContentFile(b"body {}"))
    old_name = event.custom_css.name
    event.custom_css.storage.delete(old_name)

    with log_settings_changes(event, "pretalx.event.update", person=UserFactory()):
        event.custom_css.save("other.css", ContentFile(b"a {}"))

    log = event.logged_actions().get()
    assert log.data["changes"]["custom_css"] == {"old": old_name, "new": "a {}"}


@pytest.mark.django_db
def test_settings_snapshot_falls_back_to_effective_defaults():
    event = EventFactory()
    del event.feature_flags["use_submission_comments"]
    event.save()

    with translation.override("de"):
        data = settings_snapshot(event, ReviewSettingsForm)

    assert data["feature_flags.use_submission_comments"] is True
    assert data["settings.review_help_text"] == {
        "en": "Please give a fair review on why you’d like to see this proposal "
        "at the conference, or why you think it would not be a good fit."
    }


@pytest.mark.django_db
def test_log_settings_changes_logs_only_changed_settings():
    event = EventFactory()
    user = UserFactory()

    with log_settings_changes(
        event, "pretalx.event.update", person=user, forms=(MailSettingsForm,)
    ):
        event.save()

    assert not event.logged_actions().exists()

    with log_settings_changes(
        event, "pretalx.event.update", person=user, forms=(MailSettingsForm,)
    ):
        event.mail_settings["reply_to"] = "chair@example.org"
        event.save()

    log = event.logged_actions().get()
    assert log.person == user
    assert log.data["changes"] == {
        "mail_settings.reply_to": {"old": "", "new": "chair@example.org"}
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("key", "expected_label", "expected_field"),
    (
        (
            "feature_flags.submission_public_review",
            "Allow submitters to share their proposal publicly",
            CfPSettingsForm.base_fields["submission_public_review"],
        ),
        ("feature_flags.removed_flag", "Removed flag", None),
    ),
    ids=("known", "unknown"),
)
def test_resolve_log_changes_labels_settings_keys(key, expected_label, expected_field):
    event = EventFactory()
    log = ActivityLogFactory(
        event=event,
        content_object=event,
        action_type="pretalx.event.update",
        data={"changes": {key: {"old": False, "new": True}}},
    )

    change = resolve_log_changes(log)[key]

    assert str(change["label"]) == expected_label
    assert change.get("form_field") is expected_field


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("key", "expected_label"),
    (("locales", "Active languages"), ("content_locales", "Content languages")),
)
def test_resolve_log_changes_labels_locales(key, expected_label):
    event = EventFactory()
    log = ActivityLogFactory(
        event=event,
        content_object=event,
        action_type="pretalx.event.update",
        data={"changes": {key: {"old": ["en"], "new": ["en", "de-formal"]}}},
    )

    change = resolve_log_changes(log)[key]

    assert str(change["label"]) == expected_label
    assert str(change["choices"]["de-formal"]) == "German (formal)"
