.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`user-guide-cfp`:

Call for Proposals
==================

The Call for Proposals – also known as Call for Participation, Call for Papers, or simply
CfP – is how you collect session proposals from potential speakers. pretalx provides a
submission wizard that guides speakers through the process of submitting a proposal, and
you can configure the CfP to ask for the information you need. You can find the CfP
configuration under **Your event → CfP** in the organiser interface.

.. _`user-guide-cfp-deadlines`:

Deadlines
---------

You can configure when your CfP opens and closes in the CfP settings:

**Opening date**: When set, proposals will only be accepted after this date.
Leave empty to start accepting proposals as soon as the event is live.

**Deadline**: The last date you want to accept proposals. After this date, speakers
will not be able to start new submissions. Existing drafts will also become read-only
once the CfP is closed. However, drafts created with an access code remain editable
until that code's deadline passes (see :ref:`user-guide-access-codes`).

Session types can override the global deadline with their own deadlines. If a session
type has its own deadline, that deadline takes precedence over the global CfP deadline
for submissions of that type. This lets you keep certain session types open longer than
others – for example, you might close the regular talk CfP but keep lightning talks open
for another week.

The CfP Editor
--------------

The CfP editor is the main tool for configuring your submission form. You can find it
under **Your event → CfP**. It shows you a live preview of the submission wizard as
speakers will see it, and lets you configure each step and field interactively.

In the editor, you can:

- **Set a headline and text** for each page of the CfP.
- **Add and remove fields** from the submission form. Click the button with the red x
  next to a field to remove it from the CfP, and click a field name in the “Available
  fields” column to add an unused field to the CfP.
- **Reorder fields** by dragging them into the order that makes the most sense for your
  event.
- **Configure each field** by clicking on it. You can customise the label, help text,
  and whether the field is required or optional. Text fields also let you set minimum
  and maximum length constraints. The length is counted either in characters or in words,
  depending on a setting that you can configure under **CfP → Settings**.

Some fields are managed automatically based on your event configuration: the session
type field is hidden when only one session type exists, the track field is hidden when
tracks are disabled, and the content locale field is hidden when your event has only
one language.

Built-in Fields
---------------

The submission form includes the following built-in fields. Only the title field is required
and cannot be removed, all other fields can be set to required, optional, or hidden:

- **Title**: The session title. This is the only truly mandatory field and cannot be
  removed.
- **Session type**: Format and default duration (see :ref:`Session Types
  <user-guide-session-types>`). Automatically hidden when only one session type exists.
- **Abstract**: A short summary of the session, shown in bold on public session pages.
- **Description**: A longer description, useful for workshops or sessions that need
  more context. Shown in a regular font weight below the abstract on public session pages.
- **Track**: Thematic grouping (see :ref:`user-guide-tracks`). Only available when
  tracks are enabled.
- **Duration**: Allows submitters to specify a duration for their session, which will
  be used rather than the default duration of the session type. If you configure this
  field as required, the default duration of your session types will not be shown in
  the session type dropdown.
- **Content locale**: The language the session will be held in. Hidden when the event
  has only one content language configured. You can configure your content languages
  in your event settings under **Settings → Localisation**.
- **Additional speakers**: Lets the speaker invite co-speakers by email address.
  You can configure this field to limit the maximum number of co-speakers.

On the speaker profile page, pretalx provides the following fields:

- **Name**: Like the proposal title, the name is the only truly mandatory field.
- **Biography**: The speaker's biography, shown on their public profile.
- **Profile picture**: Speakers will be asked to upload a profile picture or to
  re-use a profile picture that they uploaded for another event. Speakers will have
  to crop the picture to a square, with a central circle highlighted as guidance, as
  pretalx often uses round speaker profile pictures on public pages.
- **Availability**: When enabled, speakers provide their availability using a
  visual calendar widget during submission. pretalx uses this information to warn
  you about scheduling conflicts – see :ref:`user-guide-schedule-availabilities`
  for details.

.. _`user-guide-custom-fields`:

Custom Fields
-------------

Beyond the built-in fields, you can add **custom fields** to collect any
additional information you need. Custom fields are very flexible: you can
control their type, who they apply to, when they are required, and whether
their answers are shown publicly. Custom fields can be created, edited and seen
under **Call for Proposals → Localisation**.

Per-session and per-speaker fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each custom field targets either **sessions** or **speakers**:

**Per-session fields** are asked once for each submission. Use these for information
about the talk itself, for example:

- "What experience level is this session aimed at?"
- "Do you need any special equipment?"
- "Will you provide a hands-on workshop or a lecture?"

**Per-speaker fields** are asked once for each speaker at your event (not per
submission). Use these for information about the person, for example:

- "Do you have any dietary requirements?"
- "What is your T-shirt size?"
- "What is your Mastodon handle?"

There is a third target, **reviewer fields**, which are answered by reviewers as part
of the review process rather than by speakers.

Field types
^^^^^^^^^^^

Custom fields support the following types:

- **Text (one-line)**: A single-line text input. You can set a minimum and maximum length just like for built-in fields.
- **Multi-line text**: A larger text area for longer answers. You can set a minimum and maximum length just like for built-in fields.
- **Number**: A numeric input. You can set a minimum and a maximum here, too.
- **URL**: A web address. URL fields have special icon support (see below).
- **Date**: A date picker. You can set a minimum and maximum date that can be selected.
- **Date and time**: A combined date and time picker. You can set a minimum and maximum date and time that can be selected.
- **Yes/No**: A simple yes-or-no choice. If you make this type of field required, it shows up as a mandatory checkbox, e.g. to ask speakers to agree with your code of conduct.
- **File upload**: Lets speakers upload a file (e.g. a slide deck or a signed agreement).
- **Choose one from a list**: A radio selection of the choices you provide.
- **Choose multiple from a list**: A multi-choice selection.

For choice fields, you define the available options when creating the field.
Each option is assigned a stable identifier, which makes it safe to use choice
answers in API integrations. You can update the choices later, too, either
manually or by using a file import.

Scoping to tracks and session types
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Per-session custom fields can be scoped to specific tracks or session types. When
scoped, the field will only appear in the submission form for matching sessions.
This lets you ask different questions for different kinds of sessions – for example,
you might ask workshop submitters about required prerequisites, but not ask the same
of lightning talk submitters. Per-speaker fields always apply regardless of track or
session type, as a speaker might submit proposals to multiple tracks or session types.

Required, optional, and deadline-based
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each custom field has three "required" modes:

- **Always optional**: Speakers may skip this field.
- **Always required**: Speakers must fill in this field to submit.
- **Required after a deadline**: The field starts out optional and becomes required
  after a date you specify. This is useful for information you want to collect
  eventually but do not need at submission time, or that submitters may not have yet –
  for example, you might make arrival information optional during the CfP but required
  two weeks before the event.

There is also a **freeze after** setting: after the given date, the field becomes
read-only and speakers can no longer change their answer.

Visibility
^^^^^^^^^^

Custom fields have two visibility settings:

**Publish answers**: When enabled, answers are shown publicly on session or speaker
pages as appropriate. Use this for information your audience should see, like
a speaker's social media links or a session's experience level.

**Show answers to reviewers**: Enabled by default. When disabled, reviewers will not
see answers to this field. This is important when running anonymous reviews – you can
collect personal information (like a speaker's employer) without exposing it to
reviewers.

Social media links
^^^^^^^^^^^^^^^^^^

URL fields that are set to be shown publicly can be given an **icon** to indicate
which platform they link to. The available icons are: Bluesky, Discord, GitHub,
Instagram, LinkedIn, Mastodon, Twitter, Website, and YouTube.

When a URL field has an icon set, the speaker's answer is displayed on their public
profile page as a recognisable social media link with the corresponding icon, rather
than as a plain URL. This gives your speaker pages a polished look and makes it easy
for attendees to find speakers on their preferred platforms.

To use this, create a custom field with type **URL**, set it to **per speaker**, enable
**Publish answers**, and select the appropriate icon.

.. _`user-guide-access-codes`:

Access Codes
------------

Access codes let you extend your CfP beyond its regular rules. They are useful in
two main scenarios:

1. **Opening the CfP after the deadline**: Speakers with a valid access code can still
   submit proposals even after the CfP has closed.
2. **Granting access to restricted content**: Tracks and session types can be marked as
   requiring an access code. Only speakers who enter a matching access code will see
   these options in the submission form.

Navigate to **Your event → CfP → Access codes** to manage access codes.

An access code consists of the following settings:

- **Code**: The alphanumeric code used in a link to activate the code. pretalx generates a random code for you, but you can change it too.
- **Valid until**: An optional expiry date. After this date, the code can no longer be used to submit proposals.
- **Maximum uses**: How many times the code can be used to submit a proposal. The default is 1 (single use). Leave empty for unlimited uses.
- **Tracks**: Optionally restrict the access code to one or more tracks. When set, speakers using this code will only see these tracks in the submission form.
- **Session types**: Optionally restrict the access code to one or more session types. When set, speakers using this code will only see these session types.
- **Internal notes**: Notes visible only to organisers, e.g. who this access code was sent to.

Tracks and session types
^^^^^^^^^^^^^^^^^^^^^^^^

Both tracks and session types can be marked as "requires access code" in their
settings. When this flag is set, the track or session type will not appear in the
submission form unless the speaker has entered a matching access code.

This interacts with access code settings as follows:

- **Access code with specific tracks/types**: The speaker sees *only* those
  tracks/types, including any that require an access code.
- **Access code with no tracks/types set**: The speaker sees all tracks/types that
  do *not* require an access code. The code still lets them submit past the
  deadline, but does not unlock restricted tracks or types.
- **No access code**: The speaker sees all tracks/types that do not require an
  access code, subject to the regular deadline rules.

Distributing access codes
^^^^^^^^^^^^^^^^^^^^^^^^^

Once you have created an access code, you can distribute it to speakers in two ways:

- **Copy the link**: The access code page shows a direct submission link with the
  code pre-filled. Copy and share this link however you like.
- **Send an email**: Click "Send code by email" to send the link directly to one
  or more speakers from within pretalx. You will see an email form with a text
  generated from the access code's setting that you can modify before sending the email.
