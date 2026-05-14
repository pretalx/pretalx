# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_noop as _
from i18nfield.strings import LazyI18nString

from pretalx.mail.enums import MailTemplateRoles

GENERIC_SUBJECT = LazyI18nString.from_gettext(_("Your proposal: {submission_title}"))

ACK_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

We have received your proposal “{submission_title}” to
{event_name}. We will notify you once we have had time to consider all
proposals, but until then you can see and edit your proposal at
{submission_url}.

Please do not hesitate to contact us if you have any questions!

The {event_name} organisers""")
)

ACCEPT_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

We are happy to tell you that we accept your proposal “{submission_title}”
to {event_name}. Please click this link to confirm your attendance:

    {confirmation_link}

We look forward to seeing you at {event_name} - Please contact us if you have any
questions! We will reach out again before the conference to tell you details
about your slot in the schedule and technical details concerning the room
and presentation tech.

See you there!
The {event_name} organisers""")
)

REJECT_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

We are sorry to tell you that we cannot accept your proposal
“{submission_title}” to {event_name}. There were just too many great
proposals - we hope to see you at {event_name} as an attendee instead
of a speaker!

The {event_name} organisers""")
)

UPDATE_SUBJECT = LazyI18nString.from_gettext(_("New schedule!"))
UPDATE_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

We have released a new schedule version, and wanted to tell you:

{speaker_schedule_new}

We look forward to seeing you, and please contact us if there is any problem with your session or assigned slot.

The {event_name} organisers""")
)

QUESTION_SUBJECT = LazyI18nString.from_gettext(
    _("We have some questions about your proposal")
)
QUESTION_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

We have some open questions about yourself and your proposal that we’d
like to ask you to answer:

{questions}

You can answer them at {url}.

Please do not hesitate to contact us if you have any questions in turn!

The {event_name} organisers""")
)

NEW_SUBMISSION_SUBJECT = LazyI18nString.from_gettext(
    _("New proposal: {proposal_title}")
)
NEW_SUBMISSION_TEXT = LazyI18nString.from_gettext(
    _("""Hi,

you have received a new proposal for your event {event_name}:
“{submission_title}” by {speakers}.
You can see details at

  {orga_url}

All the best,
your {event_name} CfP system.
""")
)

SPEAKER_INVITE_SUBJECT = LazyI18nString.from_gettext(
    _("You have been added to a proposal for {event_name}")
)

NEW_SPEAKER_INVITE_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

You have been added to a proposal of {event_name}, titled “{proposal_title}”.
An account has been created for you – please follow this link to set your account password.

{invitation_link}

Afterwards, you can edit your user profile and see the state of your proposal.

The {event} orga crew""")
)
EXISTING_SPEAKER_INVITE_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

You have been added to a proposal of {event_name}, titled “{proposal_title}”.
Please follow this link to edit your user profile and see the state of your proposal:

{proposal_url}

The {event_name} organisers""")
)


DRAFT_REMINDER_SUBJECT = LazyI18nString.from_gettext(
    _("Reminder: Submit your proposal")
)
DRAFT_REMINDER_TEXT = LazyI18nString.from_gettext(
    _("""Hi!

You have started a proposal "{submission_title}" for {event_name},
but you haven't submitted it yet. Please go to

    {submission_url}

to complete and submit your proposal.

Please do not hesitate to contact us if you have any questions!

The {event_name} organisers""")
)


PASSWORD_RESET_SUBJECT = LazyI18nString.from_gettext(_("Password recovery"))
PASSWORD_RESET_TEXT = LazyI18nString.from_gettext(
    _("""Hi {name},

you have requested a new password for your pretalx account.
To reset your password, click on the following link:

  {url}

If this wasn’t you, you can just ignore this email.

All the best,
the pretalx robot""")
)

PASSWORD_CHANGED_SUBJECT = LazyI18nString.from_gettext(_("[pretalx] Password changed"))
PASSWORD_CHANGED_TEXT = LazyI18nString.from_gettext(
    _("""Hi {name},

Your pretalx account password was just changed.

If you did not change your password, please contact the site administration immediately.

All the best,
the pretalx team""")
)

EMAIL_CHANGED_SUBJECT = LazyI18nString.from_gettext(
    _("[pretalx] Email address changed")
)
EMAIL_CHANGED_TEXT = LazyI18nString.from_gettext(
    _("""Hi {name},

This is a confirmation that the email address for your pretalx account has been changed from {old_email} to {new_email}.

If you did not perform this change, please contact an administrator immediately.

All the best,
the pretalx team""")
)


CFP_CLOSED_TEXT = LazyI18nString.from_gettext(
    _("""Hi,

just writing you to let you know that your Call for Proposals is now
closed. Here is a list of links that should be useful in the next days:

- You’ll find a list of all your {submission_count} proposals here:
  {event_submissions}
- You can add reviewers here:
  {event_team}
- You can review proposals here:
  {event_review}
- And create your schedule here, once you have accepted proposals:
  {event_schedule}
""")
)

EVENT_OVER_TEXT = LazyI18nString.from_gettext(
    _("""Hi,

congratulations, your event is over! Hopefully it went well. Here are some
statistics you might find interesting:

- You had {submission_count} proposals,
- Of which you selected {talk_count} sessions.
- The reviewers wrote {review_count} reviews.
- You released {schedule_count} schedules in total.
- Over the course of the event, you sent {mail_count} emails.

If there is anything you’re missing, come tell us about it
at https://github.com/pretalx/pretalx/issues/new or via an
email to support@pretalx.com!
""")
)


DEFAULT_PHRASES = {
    MailTemplateRoles.SUBMISSION_ACCEPT: (GENERIC_SUBJECT, ACCEPT_TEXT),
    MailTemplateRoles.SUBMISSION_REJECT: (GENERIC_SUBJECT, REJECT_TEXT),
    MailTemplateRoles.NEW_SUBMISSION: (GENERIC_SUBJECT, ACK_TEXT),
    MailTemplateRoles.NEW_SUBMISSION_INTERNAL: (
        NEW_SUBMISSION_SUBJECT,
        NEW_SUBMISSION_TEXT,
    ),
    MailTemplateRoles.NEW_SCHEDULE: (UPDATE_SUBJECT, UPDATE_TEXT),
    MailTemplateRoles.QUESTION_REMINDER: (QUESTION_SUBJECT, QUESTION_TEXT),
    MailTemplateRoles.DRAFT_REMINDER: (DRAFT_REMINDER_SUBJECT, DRAFT_REMINDER_TEXT),
    MailTemplateRoles.NEW_SPEAKER_INVITE: (
        SPEAKER_INVITE_SUBJECT,
        NEW_SPEAKER_INVITE_TEXT,
    ),
    MailTemplateRoles.EXISTING_SPEAKER_INVITE: (
        SPEAKER_INVITE_SUBJECT,
        EXISTING_SPEAKER_INVITE_TEXT,
    ),
}
