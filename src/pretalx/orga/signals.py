from django.dispatch import Signal

from pretalx.common.signals import EventPluginSignal

nav_event = EventPluginSignal()
"""
This signal allows you to add additional views to the admin panel
navigation. You will get the request as a keyword argument ``request``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a ForkAwesome icon name with the key ``icon``, it will  be respected depending
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
a ForkAwesome icon name with the key ``icon``, it will  be respected depending
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

extra_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to existing forms in the
organiser backend. The signal is sent for all forms that use the
``basic_form.html`` template, which includes — but is not limited to — the
forms for tracks, session tags and types, access codes, and rooms, for example.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing and the ``instance`` that the form is working on. ``sender`` could be
``None`` if the form is not related to an event, such as the team settings form.

Receivers of this generic signal must identify the kind of form and the type
of data they are working on by checking the ``request`` or the type of the
``instance`` argument. The form extension should be used to edit data related
to the instance of the main form.

The elements of the form will be rendered inside a ``<fieldset>`` below the
existing fields of the form. If you want to add a label, you can return a form
with a ``label`` attribute set, which will be rendered as a ``<legend>``
element for the fieldset.

Separate signals are sent for submission-, speaker-, review-, and email-related
forms, which are documented in the respective sections below. These signals
are sent with the ``speaker_form``, ``submission_form``, ``review_form``, and
``mail_form`` names.

Receivers may return either a single form or a list of forms.
"""

speaker_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to speaker-related forms in
the organiser backend. Unlike the generic ``extra_form`` signal, this signal is
only sent for forms that specifically deal with speakers.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing and the ``instance`` the form is working on. The ``instance``
argument is always an instance of ``SpeakerProfile``.

This signal is only sent for speaker-related forms. For generic form
extensions, use the ``extra_form`` signal instead.

The person associated with the speaker profile is accessible via the ``user``
attribute of the ``instance`` argument. This signal is well-suited for adding
personal data fields related to the speaker, potentially even pulling
information from external systems such as ticketing platforms or CRMs.

Receivers may return either a single form or a list of forms.
"""

submission_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to submission-related forms
in the organiser backend. Unlike the generic ``extra_form`` signal, this signal
is only sent for forms that specifically deal with submissions.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing and the ``instance`` the form is working on. The ``instance``
argument is always an instance of ``Submission``.

This signal is only sent for submission-related forms. For generic form
extensions, use the ``extra_form`` signal instead.

This signal is well-suited for integrating with external ticketing or support
systems to track submission-specific communication or requirements — both
during the preparation phase and throughout the event itself. Possible use
cases include special technical arrangements or billing-related coordination.

Receivers may return either a single form or a list of forms.
"""

review_form = EventPluginSignal()
"""
This signal allows you to add custom form elements to review-related forms in
the organiser backend. Unlike the generic ``extra_form`` signal, this signal is
only sent for forms that specifically deal with reviews.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing and the ``instance`` the form is working on. The ``instance``
argument is always an instance of ``Review``.

This signal is only sent for review-related forms. For generic form
extensions, use the ``extra_form`` signal instead.

This signal is useful for capturing additional information about speakers and
submissions during the review phase. Similar to the custom fields that submitters
fill out during the CFP phase, these fields are intended solely for internal use.

Receivers may return either a single form or a list of forms.
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
