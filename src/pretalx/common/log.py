# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import string

from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields.related import ManyToManyRel, ManyToOneRel
from django.dispatch import receiver
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy as _n
from django.utils.translation import pgettext_lazy

from pretalx.common.models.log import ActivityLog
from pretalx.common.signals import activitylog_display, activitylog_object_link
from pretalx.common.text.phrases import phrases
from pretalx.event.models.event import Event
from pretalx.mail.models import MailTemplate, QueuedMail
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import (
    Answer,
    AnswerOption,
    CfP,
    Question,
    Review,
    Submission,
    SubmissionComment,
    SubmissionStates,
)


def compute_log_changes(old_data, new_data):
    old_data = old_data or {}
    new_data = new_data or {}
    all_keys = set(old_data.keys()) | set(new_data.keys())
    changes = {}

    for key in all_keys:
        old_value = old_data.get(key)
        new_value = new_data.get(key)
        if (old_value or new_value) and (old_value != new_value):
            changes[key] = {"old": old_value, "new": new_value}

    return changes


def resolve_log_changes(activitylog):
    if not activitylog.data or not activitylog.event:
        return None
    raw_changes = activitylog.data.get("changes")
    if not raw_changes:
        return None
    obj = activitylog.content_object
    if not obj:
        return None
    result = {}
    for key, value in raw_changes.items():
        display = value.copy()
        if not value.get("old") and not value.get("new"):
            continue
        if key.startswith("question-"):
            question_pk = key.split("-", 1)[-1]
            question = activitylog.event.questions.filter(pk=question_pk).first()
            if question:
                display["question"] = question
                display["label"] = question.question
        else:
            try:
                field = obj.__class__._meta.get_field(key)
                display["field"] = field
                if isinstance(field, (ManyToOneRel, ManyToManyRel)):
                    display["label"] = field.related_model._meta.verbose_name_plural
                else:
                    display["label"] = field.verbose_name
            except FieldDoesNotExist:
                display["label"] = key.capitalize()
        result[key] = display
    return result


# Map content type ``app_label.model`` to readable names used in the
# activity log filter and elsewhere.
CONTENT_TYPE_NAMES = {
    "submission.submission": _("Proposals"),
    "submission.question": _("Custom fields"),
    "submission.answerOption": _("Custom field options"),
    "submission.review": _("Reviews"),
    "submission.submissioncomment": _("Comments"),
    "submission.tag": _("Tags"),
    "submission.track": _("Tracks"),
    "submission.submissiontype": _("Session types"),
    "person.speakerprofile": _("Speakers"),
    "person.user": _("Users"),
    "mail.mailtemplate": _("Email templates"),
    "mail.queuedmail": _("Emails"),
    "schedule.room": _("Rooms"),
    "schedule.schedule": _("Schedules"),
    "schedule.talkslot": _("Slots"),
    "event.event": _("Event"),
    "cfp.cfp": _("Call for Proposals"),
    "team.team": _("Teams"),
}

# Group action types by category so the activity log filter dropdown can
# present a flat set of related actions instead of every action_type in
# isolation.
ACTION_TYPE_GROUPS = {
    _("Proposals"): [
        ("pretalx.submission.create", _("Created")),
        ("pretalx.submission.update", _("Modified")),
        ("pretalx.submission.delete", _("Deleted")),
        ("pretalx.submission.deleted", _("Deleted")),
        ("pretalx.submission.accept", _("accepted")),
        ("pretalx.submission.reject", _("rejected")),
        ("pretalx.submission.cancel", _("Cancelled")),
        ("pretalx.submission.confirm", _("confirmed")),
        ("pretalx.submission.withdraw", _("withdrawn")),
    ],
    _("Custom fields"): [
        ("pretalx.question.create", _("Created")),
        ("pretalx.question.update", _("Modified")),
        ("pretalx.question.delete", _("Deleted")),
        ("pretalx.question.activate", pgettext_lazy("history log entry", "Activated")),
        (
            "pretalx.question.deactivate",
            pgettext_lazy("history log entry", "Deactivated"),
        ),
        ("pretalx.question.reorder", _("Reordered")),
        ("pretalx.question.option.create", _("Option created")),
        ("pretalx.question.option.update", _("Option modified")),
        ("pretalx.question.option.delete", _("Option deleted")),
    ],
    _("Emails"): [
        ("pretalx.mail.create", _("Created")),
        ("pretalx.mail.update", _("Modified")),
        ("pretalx.mail.delete", _("Deleted")),
        ("pretalx.mail.sent", pgettext_lazy("email status", "Sent")),
        ("pretalx.mail_template.create", _("Template created")),
        ("pretalx.mail_template.update", _("Template modified")),
        ("pretalx.mail_template.delete", _("Template deleted")),
    ],
    pgettext_lazy("history filter category", "Schedule"): [
        ("pretalx.schedule.release", pgettext_lazy("history log entry", "Released")),
        ("pretalx.room.create", _("Room created")),
        ("pretalx.room.update", _("Room modified")),
        ("pretalx.room.delete", _("Room deleted")),
    ],
    _("Event"): [
        ("pretalx.event.create", _("Created")),
        ("pretalx.event.update", _("Modified")),
        ("pretalx.event.activate", pgettext_lazy("history log entry", "Activated")),
        ("pretalx.event.deactivate", pgettext_lazy("history log entry", "Deactivated")),
        ("pretalx.cfp.update", _("CfP modified")),
    ],
}

# Usually, we don't have to include the object name in activity log
# strings, because we use ActivityLog.content_object to get the object
# and display it above the message. However, in some cases, like when
# we log the deletion of an object, we don't have the object anymore,
# so we'll want to format the message instead.
TEMPLATE_LOG_NAMES = {
    "pretalx.event.delete": _("The event {name} ({slug}) by {organiser} was deleted."),
    "pretalx.organiser.delete": _("The organiser {name} was deleted."),
    "pretalx.access_code.send": _("The access code has been sent to {email}."),
    "pretalx.review_phase.activate": _("The review phase “{name}” was activated."),
    "pretalx.submission.invitation.send": _(
        "A speaker invitation was sent to {email}."
    ),
    "pretalx.submission.invitation.accept": _(
        "A speaker invitation to {email} was accepted."
    ),
    "pretalx.submission.invitation.retract": _(
        "A speaker invitation to {email} was retracted."
    ),
}

# These log names were used in the past, and we still support them for display purposes
LOG_ALIASES = {
    "pretalx.event.invite.orga.accept": "pretalx.invite.orga.accept",
    "pretalx.event.invite.orga.retract": "pretalx.invite.orga.retract",
    "pretalx.event.invite.orga.send": "pretalx.invite.orga.send",
    "pretalx.event.invite.reviewer.retract": "pretalx.invite.reviewer.retract",
    "pretalx.event.invite.reviewer.send": "pretalx.invite.reviewer.send",
    "pretalx.submission.answercreate": "pretalx.submission.answer.create",
    "pretalx.submission.answerupdate": "pretalx.submission.answer.update",
    "pretalx.submission.confirmation": "pretalx.submission.confirm",
    "pretalx.user.password.changed": "pretalx.user.password.update",
    # This isn't really the same thing, as the create takes place when the submission is
    # created, e.g. as a draft proposal, and the make_submitted takes place when the submission
    # is submitted to the CfP. But as we treat draft proposals as not existing at all
    # yet, we can treat this as a create action.
    "pretalx.submission.make_submitted": "pretalx.submission.create",
}

LOG_NAMES = {
    "pretalx.cfp.update": _("The CfP has been modified."),
    "pretalx.event.activate": _("The event was made public."),
    "pretalx.event.create": _("The event has been added."),
    "pretalx.event.deactivate": _("The event was deactivated."),
    "pretalx.event.delete": _("The event was deleted."),  # old data
    "pretalx.event.plugins.disabled": _("A plugin was disabled."),
    "pretalx.event.plugins.enabled": _("A plugin was enabled."),
    "pretalx.event.update": _("The event was modified."),
    "pretalx.invite.orga.accept": _("The invitation was accepted."),
    "pretalx.invite.orga.retract": _("An invitation was retracted."),
    "pretalx.invite.orga.send": _("An invitation was sent."),
    "pretalx.invite.reviewer.retract": _(
        "The invitation to the review team was retracted."
    ),
    "pretalx.invite.reviewer.send": _("The invitation to the review team was sent."),
    "pretalx.team.member.remove": _("A team member was removed"),
    "pretalx.mail.create": _("An email was created."),
    "pretalx.mail.delete": _("A pending email was deleted."),
    "pretalx.mail.delete_all": _("All pending emails were deleted."),
    "pretalx.mail.sent": _("An email was sent."),
    "pretalx.mail.update": _("An email was modified."),
    "pretalx.mail_template.create": _("An email template was added."),
    "pretalx.mail_template.delete": _("An email template was deleted."),
    "pretalx.mail_template.update": _("An email template was modified."),
    "pretalx.organiser.delete": _("The organiser was deleted."),  # old data
    "pretalx.question.create": _("A custom field was added."),
    "pretalx.question.delete": _("A custom field was deleted."),
    "pretalx.question.update": _("A custom field was modified."),
    "pretalx.question.activate": _("A custom field was activated."),
    "pretalx.question.deactivate": _("A custom field was deactivated."),
    "pretalx.question.reorder": _("The custom field order was changed."),
    "pretalx.cfp.reset": _("The CfP configuration was reset to defaults."),
    "pretalx.question.option.create": _("A custom field option was added."),
    "pretalx.question.option.delete": _("A custom field option was deleted."),
    "pretalx.question.option.update": _("A custom field option was modified."),
    "pretalx.tag.create": _("A tag was added."),
    "pretalx.tag.delete": _("A tag was deleted."),
    "pretalx.tag.update": _("A tag was modified."),
    "pretalx.room.create": _("A new room was added."),
    "pretalx.room.update": _("A room was modified."),
    "pretalx.room.delete": _("A room was deleted."),
    "pretalx.schedule.release": _("A new schedule version was released."),
    "pretalx.submission.accept": _("The proposal was accepted."),
    "pretalx.submission.cancel": _("The proposal was cancelled."),
    "pretalx.submission.confirm": _("The proposal was confirmed."),
    "pretalx.submission.create": _("The proposal was added."),
    "pretalx.submission.delete": _("The proposal has been deleted."),
    "pretalx.submission.deleted": _(
        "The proposal has been deleted."
    ),  # backwards compatibility
    "pretalx.submission.reject": _("The proposal was rejected."),
    "pretalx.submission.resource.create": _("A proposal resource was added."),
    "pretalx.submission.resource.delete": _("A proposal resource was deleted."),
    "pretalx.submission.resource.update": _("A proposal resource was modified."),
    "pretalx.submission.review.delete": _("A review was deleted."),
    "pretalx.submission.review.update": _("A review was modified."),
    "pretalx.submission.review.create": _("A review was added."),
    "pretalx.submission.speakers.add": _("A speaker was added to the proposal."),
    "pretalx.submission.speakers.invite": _("A speaker was invited to the proposal."),
    "pretalx.submission.speakers.reorder": _("The speaker order was changed."),
    "pretalx.submission.speakers.remove": _("A speaker was removed from the proposal."),
    "pretalx.submission.invitation.send": _("A speaker invitation was sent."),
    "pretalx.submission.invitation.accept": _("A speaker invitation was accepted."),
    "pretalx.submission.invitation.retract": _("A speaker invitation was retracted."),
    "pretalx.submission.unconfirm": _("The proposal was unconfirmed."),
    "pretalx.submission.update": _("The proposal was modified."),
    "pretalx.submission.withdraw": _("The proposal was withdrawn."),
    "pretalx.submission.answer.update": _("A custom field response was modified."),
    "pretalx.submission.answer.create": _("A custom field response was added."),
    "pretalx.submission.answer.delete": _("A custom field response was removed."),
    "pretalx.submission.comment.create": _("A proposal comment was added."),
    "pretalx.submission.comment.delete": _("A proposal comment was deleted."),
    "pretalx.submission_type.create": _("A session type was added."),
    "pretalx.submission_type.delete": _("A session type was deleted."),
    "pretalx.submission_type.make_default": _(
        "The session type has been made default."
    ),
    "pretalx.submission_type.update": _("A session type was modified."),
    "pretalx.access_code.create": _("An access code was added."),
    "pretalx.access_code.update": _("An access code was modified."),
    "pretalx.access_code.delete": _("An access code was deleted."),
    "pretalx.submission.signup.signup": _("An attendee signed up for the session."),
    "pretalx.submission.signup.cancel": _("An attendee cancelled their signup."),
    "pretalx.submission.signup.delete": _("An attendee signup was deleted."),
    "pretalx.track.create": _("A track was added."),
    "pretalx.track.delete": _("A track was deleted."),
    "pretalx.track.update": _("A track was modified."),
    "pretalx.speaker.arrived": _("A speaker has been marked as arrived."),
    "pretalx.speaker.unarrived": _("A speaker has been marked as not arrived."),
    "pretalx.speaker_information.create": _("A speaker information note was added."),
    "pretalx.speaker_information.update": _("A speaker information note was modified."),
    "pretalx.speaker_information.delete": _("A speaker information note was deleted."),
    "pretalx.user.token.create": _("The API token was created."),
    "pretalx.user.token.reset": _("The API token was reset."),
    "pretalx.user.token.revoke": _("The API token was revoked."),
    "pretalx.user.token.upgrade": _(
        "The API token was upgraded to the latest version."
    ),
    "pretalx.user.password.reset": phrases.base.password_reset_success,
    "pretalx.user.password.update": _("The password was modified."),
    "pretalx.user.profile.update": _("The speaker was modified."),
    "pretalx.user.email.update": _("The user changed their email address."),
}


@receiver(activitylog_display)
def default_activitylog_display(sender: Event, activitylog: ActivityLog, **kwargs):
    if templated_entry := TEMPLATE_LOG_NAMES.get(activitylog.action_type):
        message = str(templated_entry)
        # Check if all placeholders are present in activitylog.data
        placeholders = {v[1] for v in string.Formatter().parse(message) if v[1]}
        if isinstance(activitylog.data, dict) and placeholders <= set(
            activitylog.data.keys()
        ):
            return message.format(**activitylog.data)
    action_type = LOG_ALIASES.get(activitylog.action_type, activitylog.action_type)
    return LOG_NAMES.get(action_type)


def _submission_label_text(submission: Submission) -> str:
    if submission.state in (SubmissionStates.ACCEPTED, SubmissionStates.CONFIRMED):
        return _n("Session", "Sessions", 1)
    return _n("Proposal", "Proposals", 1)


@receiver(activitylog_object_link)
def default_activitylog_object_link(sender: Event, activitylog: ActivityLog, **kwargs):
    if not activitylog.content_object:
        return None
    url = ""
    text = ""
    link_text = ""
    if isinstance(activitylog.content_object, Submission):
        url = activitylog.content_object.orga_urls.base
        link_text = escape(activitylog.content_object.title)
        text = _submission_label_text(activitylog.content_object)
    elif isinstance(activitylog.content_object, SubmissionComment):
        url = (
            activitylog.content_object.submission.orga_urls.comments
            + f"#comment-{activitylog.content_object.pk}"
        )
        link_text = escape(activitylog.content_object.submission.title)
        text = _submission_label_text(activitylog.content_object.submission)
    elif isinstance(activitylog.content_object, Review):
        url = activitylog.content_object.submission.orga_urls.reviews
        link_text = escape(activitylog.content_object.submission.title)
        text = _submission_label_text(activitylog.content_object.submission)
    elif isinstance(activitylog.content_object, Question):
        url = activitylog.content_object.urls.base
        link_text = escape(activitylog.content_object.question)
        text = _("Custom field")
    elif isinstance(activitylog.content_object, AnswerOption):
        url = activitylog.content_object.question.urls.base
        link_text = escape(activitylog.content_object.question.question)
        text = _("Custom field")
    elif isinstance(activitylog.content_object, Answer):
        if activitylog.content_object.submission:
            url = activitylog.content_object.submission.orga_urls.base
        else:
            url = activitylog.content_object.question.urls.base
        link_text = escape(activitylog.content_object.question.question)
        text = _("Response to custom field")
    elif isinstance(activitylog.content_object, CfP):
        url = activitylog.content_object.urls.text
        link_text = _("Call for Proposals")
    elif isinstance(activitylog.content_object, MailTemplate):
        url = activitylog.content_object.urls.base
        text = _("Email template")
        link_text = escape(activitylog.content_object.subject)
    elif isinstance(activitylog.content_object, QueuedMail):
        url = activitylog.content_object.urls.base
        text = _("Email")
        link_text = escape(activitylog.content_object.subject)
    elif isinstance(activitylog.content_object, SpeakerProfile):
        url = activitylog.content_object.orga_urls.base
        text = _("Speaker")
        link_text = escape(activitylog.content_object.user.get_display_name())
    elif isinstance(activitylog.content_object, Event):
        url = activitylog.content_object.orga_urls.base
        text = _("Event")
        link_text = escape(activitylog.content_object.name)
    link_text = link_text or url
    url_string = f'<a href="{url}">{link_text}</a>' if url else link_text
    if text or url_string.strip():
        return f"{text} {url_string}".strip()
