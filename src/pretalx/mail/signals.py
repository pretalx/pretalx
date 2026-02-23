# SPDX-FileCopyrightText: 2021-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.signals import EventPluginSignal

register_mail_placeholders = EventPluginSignal()
"""
This signal is sent out to get all known email text placeholders. Receivers should return
an instance of a subclass of pretalx.mail.placeholder.BaseMailTextPlaceholder or a list of these.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

request_pre_send = EventPluginSignal()
"""
This signal is sent out before an email sending action is taken via the web interface –
either bulk email or individual emails. The signal is not called when emails are just
placed in the outbox without being sent.
If the email is being re-tried after a previously failed sending attempt, its ``error_data`` and
``error_timestamp`` fields will still be filled with the previous sending attempt's data.

Receivers may raise a ``pretalx.common.exceptions.SendMailException`` in order to stop
emails from being sent. The exception message (if any) will be shown to the requesting
user.

As with all event-plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the ``request`` keyword argument contains the request that
triggered the request to be sent.
"""

queuedmail_pre_send = EventPluginSignal()
"""
This signal is sent out before a ``QueuedMail`` will been sent.
Receivers may set the ``sent`` timestamp to skip sending via the regular
email backend. The email text and HTML is rendered after this signal has
been processed, so you can also alter the email’s content here.
Any exceptions raised by receivers will be ignored.

Please note that this signal is only sent for ``QueuedMail`` instances that
are saved/persisted in the database and that belong to an event. This means
that you will not receive this signals for emails like password resets or
draft reminders, or anything else that pretalx thinks should be private
between the sender and the recipient.

As with all event-plugin signals, the ``sender`` keyword argument will
contain the event. Additionally, the ``mail`` keyword argument contains
the ``QueuedMail`` instance itself.
"""

queuedmail_post_send = EventPluginSignal()
"""
This signal is sent out after a ``QueuedMail`` has been queued for delivery.
It fires in the request process (not in the Celery worker), so receivers
have access to Django's request/response cycle.

**Important:** Because email delivery happens asynchronously via Celery,
the mail will be in ``sending`` state when this signal fires — actual
delivery has not completed yet. ``mail.sent`` will be ``None`` at this
point. There is no guarantee about whether delivery will succeed or fail;
receivers that need to react to delivery outcomes should check
``mail.state`` or ``mail.has_error`` at a later point.

Return values of receivers will be ignored. Receivers must not alter any
data of the ``QueuedMail`` instance.

As with all event-plugin signals, the ``sender`` keyword argument will
contain the event. Additionally, the ``mail`` keyword argument contains
the ``QueuedMail`` instance itself.
"""
