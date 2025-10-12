# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import Signal

from pretalx.common.signals import EventPluginSignal

nav_event = EventPluginSignal()
"""
This signal allows you to add additional views to the admin panel
navigation. You will get the request as a keyword argument ``request``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a Font Awesome v4 icon name with the key ``icon``, it will  be respected depending
on the type of navigation. You should also return an ``active`` key with a boolean
set to ``True``, when this item should be marked as active. If the ``children``
key is present, the entries will be rendered as a dropdown menu.
The ``request`` object will have an attribute ``event``.

If you use this, you should read the documentation on :ref:`how to deal with URLs <urlconf>`
in pretalx.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""
nav_global = Signal()
"""
This signal allows you to add additional views to the navigation bar when no event is
selected. You will get the request as a keyword argument ``request``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a Font Awesome v4 icon name with the key ``icon``, it will  be respected depending
on the type of navigation. You should also return an ``active`` key with a boolean
set to ``True``, when this item should be marked as active. If the ``children``
key is present, the entries will be rendered as a dropdown menu.

If you use this, you should read the documentation on :ref:`how to deal with URLs <urlconf>`
in pretalx.

This is no ``EventPluginSignal``, so you do not get the event in the ``sender`` argument
and you may get the signal regardless of whether your plugin is active.
"""
activate_event = EventPluginSignal()
"""
This signal is sent out before an event goes live. It allows any installed
plugin to raise an Exception to prevent the event from going live. The
exception message will be exposed to the user. If a string value is returned, pretalx
will show it as a success message.
You will get the request as a keyword argument ``request``.
Receivers are not expected to return a response.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""
nav_event_settings = EventPluginSignal()
"""
This signal is sent out to collect additional settings sub-pages of an event.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You should also return
an ``active`` key with a boolean set to ``True``, when this item should be marked
as active.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
A second keyword argument ``request`` will contain the request object.
"""

html_head = EventPluginSignal()
"""
This signal allows you to put code inside the HTML ``<head>`` tag of every page in the
organiser backend. You will get the request as the keyword argument ``request`` and are
expected to return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the signal will be called with the ``request`` it is processing.
The receivers are expected to return HTML.
"""

html_above_orga_page = EventPluginSignal()
"""
This signal is sent out to display additional information on every page in the
organiser backend, above all other content.

This is intended for important, somewhat urgent messages that should be displayed
prominently, such as a warning about an upcoming deadline or a change in the event
schedule.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the signal will be called with the ``request`` it is processing.
The receivers are expected to return HTML.
"""

html_below_orga_page = EventPluginSignal()
"""
This signal is sent out to display additional information on every page in the
organiser backend, below all other content.

This is intended to show additional information that is not as urgent as the
information displayed by the ``html_above_orga_page`` signal, such as additional
information about individual sessions or speakers.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the signal will be called with the ``request`` it is processing.
The receivers are expected to return HTML.
"""

event_copy_data = EventPluginSignal()
"""
This signal is sent out when a new event is created as a clone of an existing event, i.e.
the settings from the older event are copied to the newer one. You can listen to this
signal to copy data or configuration stored within your plugin's models as well.

You don't need to copy data inside the general settings storage which is cloned automatically,
but you might need to modify that data.

The ``sender`` keyword argument will contain the event of the **new** event. The ``other``
keyword argument will contain the event slug to **copy from**. The keyword arguments
``submission_type_map``, ``question_map``, ``track_map`` and ``speaker_information_map`` contain
mappings from object IDs in the original event to objects in the new event of the respective
types.
"""

speaker_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to the speaker form in the organiser
backend.

Receivers may return either a single form or a list of forms. Forms with a ``label``
attribute will be rendered with this label as heading.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the signal will be called with the ``request`` it is processing and the
``instance`` the form is working on. The ``instance`` argument is a ``SpeakerProfile``
object, and you can use its ``user`` attribute to access the speaker's user account.
"""

submission_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to the submission detail form in the
organiser backend.

Receivers may return either a single form or a list of forms. Forms with a ``label``
attribute will be rendered with this label as heading.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the signal will be called with the ``request`` it is processing and the
``instance`` (of type ``Submission``) the form is working on.
"""

review_form = EventPluginSignal()
"""

This signal allows you to add custom form elements to the review form that reviewers are
presented with when reviewing proposals in the organiser backend.

Receivers may return either a single form or a list of forms. Forms with a ``label``
attribute will be rendered with this label as heading.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the signal will be called with the ``request`` it is processing and the
``instance`` the form is working on. The ``instance`` argument is always an instance of
``Review``, and you can access ``instance.submission`` to access the submission.
"""

mail_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to email-related forms in
the organiser backend. Unlike the generic ``extra_form`` signal, this signal is
only sent for forms that specifically deal with emails.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing and the ``instance`` the form is working on. The ``instance``
argument is always an instance of ``QueuedMail``.

This signal is only sent for email-related forms. For generic form
extensions, use the ``extra_form`` signal instead.

This signal can, for example, be used to integrate with an external ticketing
system used for speaker communication, by adding fields to store or display
related ticket information directly in the email form.

Receivers may return either a single form or a list of forms.
"""

dashboard_tile = EventPluginSignal()
"""
This signal is sent out to collect additional tiles for the main dashboard of an
event. Receivers are expected to return a dictionary or a list of dictionaries.

The dictionaries should contain at least the keys ``large`` for a tile heading and
``small`` for a subtitle or content. Optionally, you can return a ``url`` key to make
the tile clickable and a ``priority`` to determine the order in which tiles are
displayed. The ``priority`` should be a number between 0 and 100, with lower numbers
being displayed first. Actions should be between 10 and 30, with 20 being the
"Go to CfP" action. General statistics start at 50.
The tile dictionary may optionally also contain a ``left`` or ``right`` key, which
should contain a dictionary with the keys ``text`` and optionally ``url`` and
``color``. The ``text`` key will be displayed as a button on the left or right side
of the tile, the optional ``url`` key will make the button clickable, and the
``color`` key should be one of ``success``, `info``, ``error`` or ``secondary``.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""
