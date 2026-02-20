.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`user-guide-emails`:

Emails
======

pretalx sends emails on your behalf at several points in the event lifecycle:
when a speaker submits a proposal, when you accept or reject sessions, when
you release a schedule, and whenever you compose a message to a group of
speakers.

.. _`user-guide-emails-outbox`:

The Outbox
----------

The single most important concept in pretalx's email system is the **outbox**.
Almost every email pretalx generates on your behalf lands here first, as a
draft, rather than being sent immediately. This gives you the chance to review,
edit, or discard emails before they reach anyone.

The only exceptions are:

- **Submission confirmations**: When a speaker submits a proposal, the
  acknowledgement email is sent immediately, because speakers expect instant
  feedback that their submission went through.
- **Team emails**: Emails to your team members and reviewers are always sent
  directly (see :ref:`composing emails <user-guide-emails-compose>` below).

Everything else – acceptance emails, rejection emails, schedule notifications,
speaker invitations, and all messages you compose – goes to the outbox first.
You can find it under **Your event → Mails → Outbox**, where a badge in the
sidebar shows the number of pending (unsent) emails.

Why the outbox?
^^^^^^^^^^^^^^^

Queuing emails before sending has several advantages:

- **Review before sending**: You can read each email, fix typos, adjust
  wording for a specific speaker, or add a personal note before it goes out.
- **Batch control**: When you accept or reject 50 proposals, you get 50 draft
  emails in your outbox. You can send them all at once when you are ready, or
  hold them back while you finalise your programme.
- **Safe corrections**: Changed your mind about a rejection? Just delete the
  email from the outbox – the speaker will never know.

Working with the outbox
^^^^^^^^^^^^^^^^^^^^^^^

The outbox list shows each pending email with its subject, recipients, and
related proposals. You can **open and edit** all fields of an unsent email,
including the subject, body, Reply-To, CC and BCC headers.

You can **filter the list** by track or search for recipients, email addresses or
subjects. You can **send all unsent emails**, and if you have previously applied
filters, only the visible, matching emails are sent. This is useful if you
want to send acceptance emails for one track at a time, for example.

Discarding all or some emails works the same way as sending them.
You can also send or discard an individual email by clicking the buttons next to it.

.. _`user-guide-emails-templates`:

Email Templates
---------------

Email templates define the default text for emails that pretalx generates
automatically. You manage templates under **Your event → Mails → Templates**.

Built-in templates
^^^^^^^^^^^^^^^^^^

pretalx creates the following templates for every new event:

**Acknowledge proposal submission**
  Sent immediately when a speaker submits a proposal. Confirms receipt and
  links to the proposal page.

**Proposal accepted**
  Generated when you accept a proposal. Contains a confirmation link for the
  speaker to confirm their attendance (see :ref:`session lifecycle
  <user-guide-proposals>`).

**Proposal rejected**
  Generated when you reject a proposal.

**Add a speaker to a proposal (new account)**
  Sent when you add a speaker whose email address is not yet known to pretalx.
  Contains a link to set up their account.

**Add a speaker to a proposal (existing account)**
  Sent when you add a speaker who already has a pretalx account. Links to the
  proposal page.

**Custom fields reminder**
  Used when you send reminders for unanswered custom fields (see
  :ref:`custom fields <user-guide-custom-fields>`).

**Draft proposal reminder**
  Used when you send reminders to speakers who started a proposal but never
  submitted it.

**New schedule published**
  Generated when you release a new schedule version and choose to notify
  speakers (see :ref:`scheduling <user-guide-schedule>`).

You can edit any built-in template to match your event's tone and branding.

Custom templates
^^^^^^^^^^^^^^^^

You can create additional templates for emails you send regularly – for
example, a "Please upload your slides" reminder or a "Speaker dinner
invitation". Custom templates appear in the template list alongside the
built-in ones, and can be used as starting points in the
:ref:`email composer <user-guide-emails-compose>`.

You can use any of your templates as a starting point in the composer. In the
template list, click the "Compose" button next to a template to open the
composer with that template's subject and text pre-filled. You can then adjust
the text and select your recipients.

.. note::
    Changing a template does not affect emails that are already in the outbox.
    Those emails contain the rendered text from the moment they were generated.
    If you need to update pending emails, discard them from the outbox and
    regenerate them.

.. _`user-guide-emails-placeholders`:

Placeholders
------------

Placeholders are dynamic values enclosed in curly braces, like
``{proposal_title}`` or ``{event_name}``. When pretalx generates an email from
a template, each placeholder is replaced with the actual value for the
recipient and proposal.

You can use placeholders in both the subject and body of a template. Using a
placeholder that is not available for a given template will result in an error
when the email is generated.

Placeholders range from simple values like ``{event_name}`` or
``{proposal_title}`` to more complex ones like ``{confirmation_link}`` (a URL
the speaker clicks to confirm their attendance), ``{all_reviews}`` (all review
texts for a proposal, separated by dividers – useful for sharing reviewer
feedback in acceptance or rejection emails), or ``{speaker_schedule_full}`` (a
formatted list of all the speaker's scheduled sessions with times and rooms).

The template editor shows which placeholders are available for the template you
are editing, grouped by category. Click the **question mark** next to a
placeholder to see an explanation and a preview of what it will look like in a
real email. Some built-in templates have additional role-specific placeholders
that only appear when editing that template.

If you choose to copy a previous event's settings when setting up your new
event, email templates will be copied to the new event, which is why you may
want to use a placeholder like ``{event_name}`` – this way, when your next
event rolls around, you will not have to update the event name in all of your
email templates.

.. _`user-guide-emails-compose`:

Composing Emails
----------------

The email composer lets you write and send emails to groups of speakers,
submitters, or team members. You can find it under **Your event → Mails →
Compose emails**.

When you open the composer, you choose one of two modes:

Sessions, proposals, speakers
  Send emails to speakers based on their proposals. You can filter recipients
  by proposal state (submitted, accepted, confirmed, rejected, withdrawn),
  session type, track, content locale, and tags. You can also select specific
  proposals or speakers to include regardless of the filters.

  If you have a custom field, you can filter by custom field responses too –
  navigate to a submission list filtered by a custom field response, and use
  the "Send email" button there.

  This mode supports all placeholders, so each speaker receives a personalised
  email with their proposal details filled in.

Reviewers and team members
  Send emails to your team. Select one or more teams as recipients. These
  emails are always sent directly (they do not go through the outbox), because
  they are internal communication rather than speaker-facing messages.


Preview and deduplication
^^^^^^^^^^^^^^^^^^^^^^^^^

Before sending, click **Preview email** to see a rendered preview of the email
with sample values for all placeholders. The preview also shows the approximate
number of recipients.

The number of recipients is only approximate because, when you send an email to
a group of speakers, pretalx deduplicates automatically: if a speaker has
multiple proposals that match your filters, and the rendered email text is
identical for each (for example because you do not mention the session title),
they receive only one copy of the email. The email is still linked to all
matching proposals in the outbox.

Sending directly vs. sending to the outbox
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, composed emails are placed in the outbox for review. If you want
to send them right away, check **Send immediately**. There is no further
confirmation step after this, so be very sure that you are happy with the
email content and are sure you have selected the correct group of recipients!

Sent Emails
-----------

All sent emails are recorded under **Your event → Mails → Sent emails**, where
you can search and filter them just like the outbox. You can also click **Copy
to draft** on any sent email to create a new draft based on it, which is useful
for follow-up messages or corrections. The draft will use the original template (with placeholders intact), not the
rendered text that was sent, so you can re-personalise the message for different
recipients.

.. _`user-guide-emails-settings`:

Email Settings
--------------

You configure email settings under **Your event → Settings → Mail**.

Reply-To address
   The email address that recipients see as the reply-to address. If left
   empty, your event's main email address is used. Note that only the
   ``Reply-To`` header can be configured – the ``From`` header is always set to
   the pretalx server's sending address. Emails that claim to be ``From:`` a
   different domain than the one actually sending them are routinely flagged as
   spam or rejected outright by receiving mail servers. If you need emails to
   originate from your own domain, configure a custom mail server (see below).

Subject prefix
   A short label prepended in ``[brackets]`` to all outgoing email subjects,
   helping recipients filter emails by event. By default, pretalx uses your
   event's name as the prefix. If you or a plugin manually add a bracketed
   prefix to a template or composed email, pretalx detects this and skips the
   automatic prefix so that emails never end up with duplicate ``[brackets]``.

Signature
   Text appended to every outgoing email. pretalx automatically inserts the
   standard signature separator above it. You can use Markdown
   formatting in the signature.

Custom email server
^^^^^^^^^^^^^^^^^^^

By default, pretalx sends emails through the server configured by your
instance administrator. If you want emails to originate from your own domain,
you can configure a custom SMTP server under the mail settings.

When a custom server is configured, **all event-related emails** are routed
through it – acceptance and rejection notifications, composed messages,
schedule updates, and so on. The only exception is **password reset and
recovery emails**, which always use the system mail server, because user
accounts are valid across all events on the instance, not tied to a single
event.

Make sure your mail server is functional and reliable before enabling it.
Misconfigured or unreliable servers can cause speakers to miss important
emails with no indication to you that delivery failed. Use the **Test** button
to verify your settings, and monitor your server's delivery logs after
switching over.

.. _`user-guide-emails-deliverability`:

Email Deliverability
--------------------

When you accept or reject a large number of proposals at once, pretalx
generates one email per speaker. Sending hundreds of emails in a short window
can damage your sending domain's reputation with email providers, causing
future emails to land in spam or be rejected outright.

This is especially problematic when using a custom email server, because you
are fully responsible for your domain's reputation, including SPF, DKIM, and
DMARC records, IP warm-up, and bounce handling.

A few things you can do to protect your reputation:

- **Spread your sends**: Rather than sending all acceptance and rejection emails
  at the same time, use the outbox filters to send by track or session type
  across several hours or even days.
- **Check your DNS records**: Make sure your domain has correct SPF, DKIM, and
  DMARC records. Your email provider can usually help you with this.
- **Monitor bounces**: If you see a lot of bounced emails, investigate before
  sending more.

.. note::

   If you use `pretalx.com <https://pretalx.com>`_, email deliverability is
   handled for you. We maintain the sending infrastructure, monitor reputation,
   manage DNS records, and handle bounces automatically. We also route emails
   through specialised providers depending on the recipient to ensure the best
   possible delivery rates – for example, certain large email providers require
   specific sending paths that we maintain on your behalf.
