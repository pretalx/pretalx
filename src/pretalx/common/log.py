# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import functools
import string
from contextlib import contextmanager, suppress

from django.contrib.humanize.templatetags.humanize import naturalday
from django.core.exceptions import FieldDoesNotExist
from django.core.files import File
from django.db.models import ForeignKey, ManyToManyField, Model
from django.db.models.fields.related import ManyToManyRel, ManyToOneRel
from django.dispatch import receiver
from django.utils.html import escape
from django.utils.text import capfirst
from django.utils.timezone import localtime, now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy as _n
from django.utils.translation import pgettext_lazy
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretalx.common.language import get_locale_name
from pretalx.common.models.log import ActivityLog
from pretalx.common.models.mixins import serialize_log_value
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

EXTRA_CHANGE_LABELS = {"user_email": _("Account email")}


def resolve_foreign_key(field, value):
    if not value or not isinstance(field, ForeignKey):
        return value

    related_model = field.related_model
    with suppress(Exception):
        obj = related_model.objects.get(pk=value)
        return str(obj)

    return value


def resolve_many_to_many(field, values):
    if not values or not isinstance(field, ManyToManyField):
        return values

    objects = {}
    with suppress(Exception):
        objects = field.related_model.objects.in_bulk(values)
    return ", ".join(str(objects.get(value, value)) for value in values)


def log_values_equal(old_value, new_value):
    # i18n strings can be stored as plain strings or single-language dicts.
    # Showing this as an update is confusing and useless.
    if old_value == new_value:
        return True
    for plain, i18n in ((old_value, new_value), (new_value, old_value)):
        if (
            isinstance(plain, str)
            and isinstance(i18n, dict)
            and len(i18n) == 1
            and next(iter(i18n.values())) == plain
        ):
            return True
    return False


def compute_log_changes(old_data, new_data):
    old_data = old_data or {}
    new_data = new_data or {}
    changes = {}

    for key in new_data | old_data:
        old_value = old_data.get(key)
        new_value = new_data.get(key)
        if (old_value or new_value) and not log_values_equal(old_value, new_value):
            changes[key] = {"old": old_value, "new": new_value}

    return changes


def settings_keys(*forms):
    keys = []
    for form in forms:
        keys += [
            f"{path}.{name}"
            for name, path in getattr(form.Meta, "json_fields", {}).items()
        ]
        keys += [
            f"settings.{name}" for name in getattr(form.Meta, "hierarkey_fields", ())
        ]
    return keys


def settings_fields(*form_classes):
    return {
        key: form_class.base_fields[key.split(".", 1)[1]]
        for form_class in form_classes
        for key in settings_keys(form_class)
    }


@functools.cache
def settings_form_fields():
    from pretalx.event.interfaces.forms.event import (  # noqa: PLC0415 -- circular import
        EventForm,
    )
    from pretalx.mail.interfaces.forms.config import (  # noqa: PLC0415 -- circular import
        MailSettingsForm,
    )
    from pretalx.orga.forms.cfp import (  # noqa: PLC0415 -- circular import
        CfPForm,
        CfPSettingsForm,
    )
    from pretalx.submission.interfaces.forms.review import (  # noqa: PLC0415 -- circular import
        ReviewSettingsForm,
    )

    return {
        Event: settings_fields(
            EventForm, CfPSettingsForm, MailSettingsForm, ReviewSettingsForm
        )
        | {key: EventForm.base_fields[key] for key in ("locales", "content_locales")},
        CfP: settings_fields(CfPForm),
    }


def serialize_setting_value(value, locales):
    match value:
        case LazyI18nString(data=LazyI18nString.LazyGettextProxy()):
            value = LazyI18nString({locale: value.data[locale] for locale in locales})
        case File():
            return value.name
    return serialize_log_value(value)


def custom_css_text(file):
    if not file:
        return ""
    try:
        with file.open() as fp:
            return fp.read().decode()
    except (OSError, UnicodeDecodeError):
        return file.name


def settings_snapshot(obj, *forms):
    data = obj.get_instance_data()
    columns = {}
    for key in settings_keys(*forms):
        path, name = key.split(".", 1)
        if path in data:
            columns.setdefault(path, set()).add(name)
            values = data[path] or {}
            if name in values:
                data[key] = values[name]
            else:
                data[key] = obj._meta.get_field(path).default().get(name)
        else:
            data[key] = serialize_setting_value(
                getattr(getattr(obj, path), name), obj.locales
            )
    for column, broken_out in columns.items():
        data[column] = {
            key: value
            for key, value in (data[column] or {}).items()
            if key not in broken_out
        }
    return data


@contextmanager
def log_settings_changes(obj, action, *, person, forms=(), force=False):
    old_obj = obj.__class__.objects.get(pk=obj.pk)
    old_data = settings_snapshot(old_obj, *forms)
    yield
    new_data = settings_snapshot(obj, *forms)
    if old_data.get("custom_css") != new_data.get("custom_css"):
        old_data["custom_css"] = custom_css_text(old_obj.custom_css)
        new_data["custom_css"] = custom_css_text(obj.custom_css)
    log = obj.log_action(
        action, person=person, orga=True, old_data=old_data, new_data=new_data
    )
    if force and not log:
        obj.log_action(action, person=person, orga=True)


def resolve_log_changes(activitylog):
    if not activitylog.data:
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
            question = None
            if activitylog.event:
                question_pk = key.split("-", 1)[-1]
                question = activitylog.event.questions.filter(pk=question_pk).first()
            if question:
                display["question"] = question
                display["label"] = question.question
        elif form_field := settings_form_fields().get(type(obj), {}).get(key):
            display["form_field"] = form_field
            display["label"] = form_field.label
            if key in ("locales", "content_locales"):
                locale_names = dict(obj.available_content_locales)
                display["choices"] = {
                    code: get_locale_name(code, locale_names) for code in locale_names
                }
        elif "." in key:
            display["label"] = key.split(".")[-1].replace("_", " ").capitalize()
        else:
            try:
                field = obj.__class__._meta.get_field(key)
                display["field"] = field
                if isinstance(field, (ManyToOneRel, ManyToManyRel)):
                    display["label"] = field.related_model._meta.verbose_name_plural
                else:
                    display["label"] = field.verbose_name
                match field:
                    case ForeignKey():
                        display["old_display"] = resolve_foreign_key(
                            field, value.get("old")
                        )
                        display["new_display"] = resolve_foreign_key(
                            field, value.get("new")
                        )
                    case ManyToManyField():
                        display["old_display"] = resolve_many_to_many(
                            field, value.get("old")
                        )
                        display["new_display"] = resolve_many_to_many(
                            field, value.get("new")
                        )
            except FieldDoesNotExist:
                display["label"] = EXTRA_CHANGE_LABELS.get(key) or key.capitalize()
        result[key] = display
    return result


ACTION_LABELS = {
    "create": _("Created"),
    "update": _("Modified"),
    "delete": _("Deleted"),
    "deleted": _("Deleted"),
    **{
        action.removeprefix("."): SubmissionStates(state).label
        for state, action in SubmissionStates.log_actions.items()
    },
    "activate": pgettext_lazy("history log entry", "Activated"),
    "deactivate": pgettext_lazy("history log entry", "Deactivated"),
    "reorder": _("Reordered"),
    "release": pgettext_lazy("history log entry", "Released"),
    "sent": pgettext_lazy("email status", "Sent"),
    "skipped": pgettext_lazy("email status", "Not sent"),
    "hide": _("Room hidden"),
    "unhide": _("Room made visible"),
    "option.create": _("Option created"),
    "option.update": _("Option modified"),
    "option.delete": _("Option deleted"),
    "signup.signup": _("Signed up"),
    "signup.cancel": _("Signup cancelled"),
    "signup.delete": _("Signup deleted"),
}


def action_type_label(action_type: str) -> str:
    parts = action_type.split(".")
    action = ".".join(parts[2:]) or parts[-1]
    if label := ACTION_LABELS.get(action):
        return capfirst(label)
    return capfirst(action.replace(".", " ").replace("_", " "))


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
    "pretalx.event.invite.orga.retract": "pretalx.team.invite.orga.retract",
    "pretalx.invite.orga.retract": "pretalx.team.invite.orga.retract",
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
    "pretalx.team.invite.orga.retract": _("An invitation was retracted."),
    "pretalx.invite.orga.send": _("An invitation was sent."),
    "pretalx.invite.reviewer.retract": _(
        "The invitation to the review team was retracted."
    ),
    "pretalx.invite.reviewer.send": _("The invitation to the review team was sent."),
    "pretalx.team.remove_member": _("A team member was removed"),
    "pretalx.team.delete": _("The team was deleted."),
    "pretalx.mail.create": _("An email was created."),
    "pretalx.mail.delete": _("A pending email was deleted."),
    "pretalx.mail.delete_all": _("All pending emails were deleted."),
    "pretalx.mail.sent": _("An email was sent."),
    "pretalx.mail.skipped": _(
        "An email was not sent to this speaker because they have no email address."
    ),
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
    "pretalx.review_phase.activate": _("A review phase was activated."),
    "pretalx.review_phase.delete": _("A review phase was deleted."),
    "pretalx.room.create": _("A new room was added."),
    "pretalx.room.update": _("A room was modified."),
    "pretalx.room.delete": _("A room was deleted."),
    "pretalx.room.hide": _("A room was hidden."),
    "pretalx.room.unhide": _("A room was made visible again."),
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
    "pretalx.speaker.create": _("A speaker was created."),
    "pretalx.speaker.arrived": _("A speaker has been marked as arrived."),
    "pretalx.speaker.unarrived": _("A speaker has been marked as not arrived."),
    "pretalx.speaker.invite.send": _("A speaker invitation was sent."),
    "pretalx.speaker.invite.retract": _("A speaker invitation was retracted."),
    "pretalx.speaker.invite.invalidate": _(
        "A speaker invitation was invalidated because the contact email address changed."
    ),
    "pretalx.speaker.claim": _("The speaker claimed their profile."),
    "pretalx.speaker.delete": _("A speaker was deleted."),
    "pretalx.speaker.merge": _(
        "The speaker was merged into an existing speaker account."
    ),
    "pretalx.speaker_information.create": _("A speaker information note was added."),
    "pretalx.speaker_information.update": _("A speaker information note was modified."),
    "pretalx.speaker_information.delete": _("A speaker information note was deleted."),
    "pretalx.user.attendee.delete": _("An attendee profile was deleted."),
    "pretalx.user.token.create": _("The API token was created."),
    "pretalx.user.token.reset": _("The API token was reset."),
    "pretalx.user.token.revoke": _("The API token was revoked."),
    "pretalx.user.token.update": _("The API token was modified."),
    "pretalx.user.token.upgrade": _(
        "The API token was upgraded to the latest version."
    ),
    "pretalx.user.password.reset": phrases.base.password_reset_success,
    "pretalx.user.password.update": _("The password was modified."),
    "pretalx.user.profile.update": _("The speaker was modified."),
    "pretalx.user.email.update": _("The user changed their email address."),
    "pretalx.user.email.verification.send": _("A verification email was sent."),
    "pretalx.user.email.verification.confirm": _("The email address was verified."),
    "pretalx.user.email.verification.correct": _(
        "The unverified email address was corrected."
    ),
    "pretalx.user.email.verification.promote": _("The email address was verified."),
    "pretalx.user.email.verification.set": _(
        "The email verification state was set by an administrator."
    ),
    "pretalx.user.email.change.request": _("An email address change was requested."),
    "pretalx.user.email.change.confirm": _("The email address change was confirmed."),
    "pretalx.user.email.change.cancel": _("The email address change was cancelled."),
    "pretalx.user.email.change.taken": _(
        "The email address change was cancelled because the address is already in use."
    ),
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


def generic_object_url(obj) -> str:
    if obj is None or type(obj).__str__ is Model.__str__:
        return ""
    for attribute in ("orga_urls", "urls"):
        urls = getattr(obj, attribute, None)
        if urls is not None:
            with suppress(Exception):
                return str(urls.base)
    return ""


def activitylog_object_parts(activitylog: ActivityLog):
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
        link_text = escape(activitylog.content_object.get_display_name())
    elif isinstance(activitylog.content_object, Event):
        url = activitylog.content_object.orga_urls.base
        text = _("Event")
        link_text = escape(activitylog.content_object.name)
    elif url := generic_object_url(activitylog.content_object):
        link_text = escape(str(activitylog.content_object))
    link_text = link_text or url
    return text, url, link_text


def activitylog_entry(
    activitylog: ActivityLog, hide_object_models=(), with_objects=True
):
    object_url = object_text = object_html = ""
    content_object = activitylog.content_object if with_objects else None
    if content_object and not isinstance(content_object, hide_object_models):
        __, object_url, object_text = activitylog_object_parts(activitylog)
        if not object_url and not object_text:
            object_html = activitylog.display_object
    return {
        "log": activitylog,
        "object_url": object_url,
        "object_text": object_text,
        "object_html": object_html,
    }


def speaker_names_for_logs(log_entries):
    # Speakers are known under their event name, but may have a different
    # account name. Event-scoped logs should use the event name.
    pairs = {
        (activitylog.event_id, activitylog.person_id)
        for activitylog in log_entries
        if activitylog.event_id and activitylog.person_id
    }
    if not pairs:
        return {}
    with scopes_disabled():
        profiles = (
            SpeakerProfile.objects.filter(
                event_id__in={event_id for event_id, __ in pairs},
                user_id__in={user_id for __, user_id in pairs},
            )
            .exclude(name=None)
            .exclude(name="")
            .values_list("event_id", "user_id", "name")
        )
    return {
        (event_id, user_id): name
        for event_id, user_id, name in profiles
        if (event_id, user_id) in pairs
    }


def group_activity_log(log_entries, hide_object_models=(), with_objects=True):
    """Group log entries into day buckets."""
    log_entries = list(log_entries)
    speaker_names = speaker_names_for_logs(log_entries)
    today = localtime(now()).date()
    groups = []
    for activitylog in log_entries:
        if activitylog.person_id:
            activitylog.__dict__["person_display_name"] = (
                speaker_names.get((activitylog.event_id, activitylog.person_id))
                or activitylog.person.get_display_name()
            )
        timestamp = localtime(activitylog.timestamp)
        day = timestamp.date()
        if not groups or groups[-1]["date"] != day:
            date_format = "M j" if day.year == today.year else "M j, Y"
            groups.append(
                {
                    "date": day,
                    "label": capfirst(naturalday(timestamp, date_format)),
                    "entries": [],
                }
            )
        groups[-1]["entries"].append(
            activitylog_entry(activitylog, hide_object_models, with_objects)
        )
    return groups


@receiver(activitylog_object_link)
def default_activitylog_object_link(sender: Event, activitylog: ActivityLog, **kwargs):
    if not activitylog.content_object:
        return None
    text, url, link_text = activitylog_object_parts(activitylog)
    url_string = f'<a href="{url}">{link_text}</a>' if url else link_text
    if text or url_string.strip():
        return f"{text} {url_string}".strip()
