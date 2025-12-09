.. SPDX-FileCopyrightText: 2019-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`user-faq`:

FAQ
===

This document collects issues that came up in the past, and that cannot be
solved in pretalx with a reasonable amount of effort or time.

Sessions
--------

What is the difference between tracks and session types?
    Tracks are a way to group sessions by topic, and will be shown in the
    schedule as colour-coded blocks. Session types are a way to determine
    the format and default duration of a session. See more in the
    :ref:`Session user guide <user-guide-tracks>`.

What is the difference between the “accepted” and “confirmed” session status?
    The “accepted” status is used to indicate that a session has been
    accepted by the program committee. The “confirmed” status is used to
    indicate that the speaker has confirmed their participation in the
    conference. The “confirmed” status is set by the speaker, though organisers
    can also set it manually. See more in the :ref:`Session user guide <user-guide-proposals>`.

How do I designate sessions as fallback/alternates?
    To designate sessions as fallback or alternates, you can use the **pending states** feature.
    To do so, leave the session in the “submitted” state, but set it to “pending accepted”.
    Pending states are not shown to speakers, but you can write an email to all speakers with
    proposals marked as “pending accepted” if you want to communicate this decision.
    For more details on how to manage session states, see the
    :ref:`Session Lifecycle <user-guide-proposals-pending>` section in the
    :ref:`Sessions & Proposals <user-guide-proposals>` guide.


Schedule
--------

How can I export my schedule to PDF / print my schedule?
    pretalx does not currently offer a PDF export of the schedule, because of the level of complexity
    that comes with printing a schedule with an arbitrary amount of rooms.
    However, the schedule editor page has print support, hiding the usual pretalx UI elements like the
    menu sidebar. Combined with the schedule editor’s support for hiding rooms, this is the best PDF
    version of the schedule pretalx offers. To use it, navigate to your schedule editor, select your
    browser’s print dialogue, and then select “Print to PDF”.

How do I display poster sessions on my schedule?
    pretalx does not currently support grouping individual poster sessions into a larger "Poster Session" block.
    However, you can work around this limitation using the :ref:`featured sessions <user-guide-featured-sessions>` feature:

    1. Mark all your poster sessions as featured by checking the "Featured" checkbox on the session list page.
    2. Configure your event's "Show featured sessions page" setting (found in Settings → Display) to "Always" so the featured sessions page remains accessible to attendees.
    3. Create a placeholder poster session in your schedule (e.g., "Poster Session - See Featured Sessions") and include a link to your featured sessions page in the session description.

    This approach gives your poster sessions their own dedicated page while providing a clear reference point in the main schedule.


Email
-----

We run into issues when using Gmail.
    In Google’s eyes, pretalx is a `less secure app`_, which you'll have to
    grant special access. Even then, Gmail is known to unexpectedly block your
    SMTP connection with unhelpful error messages if you use it to send out too
    many emails in bulk (e.g. all rejections for a conference) even on GSuite,
    so using Gmail for transactional email is a bad idea.

How does pretalx choose the email language for multilingual events?
    pretalx has two distinct language settings: **event languages** (which determine available
    interface languages and are more limited, as they require a translation) and **content
    languages** (which determine the languages that can be assigned to sessions). Additionally,
    emails can refer to a specific session (using placeholders like ``{session_title}``), to
    multiple sessions (using placeholders like ``{speaker_schedule_new}``), or to no session at
    all (using only placeholders specific to the person or the overall event).

    For emails sent for **one specific proposal** (e.g. the acceptance email), the language is
    chosen as follows:

    1. The language of the proposal (its “content locale” field), if it is one of the event languages.
    2. If the proposal language is not one of the event languages, the speaker’s user interface language is used, if it is one of the event languages.
    3. As a fallback, the main event language is used.

    For emails that **do not relate to one specific proposal** (e.g. the schedule update notification,
    which can concern multiple proposals, or emails sent without any proposal context), the first
    point does not apply. In this case, the user’s interface language is used if it is one of the
    event languages, falling back to the main event language otherwise.


Integrations
------------

How do we create speaker tickets with pretix?
    As there is no direct integration between pretix and pretalx yet (some details
    here `on GitHub`_), the best way to send pretix vouchers to all your pretalx
    speakers is to use the pretalx CSV export.
    Select all accepted and confirmed speakers, and export the name and email
    field. You can then use the bulk voucher form in pretix with the exported
    CSV file directly – you can find more information on the bulk voucher
    sending workflow in the `pretix documentation`_.


.. _less secure app: https://support.google.com/accounts/answer/6010255
.. _on GitHub: https://github.com/pretalx/pretalx/discussions/2027#discussioncomment-13145751
.. _pretix documentation: https://docs.pretix.eu/guides/vouchers/#sending-out-vouchers-via-email
