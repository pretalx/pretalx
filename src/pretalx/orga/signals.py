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

dashboard_tile = EventPluginSignal()
"""
This signal is sent out to collect additional tiles for the main dashboard of an
event. Receivers are expected to return a dictionary or a list of dictionaries.

The dictionaries should contain at least the keys ``large`` for a tile heading and
``small`` for a subtitle or content. Optionally, you can return a ``url`` key to make
the tile clickable and a ``priority`` to determine the order in which tiles are
displayed. The ``priority`` should be a number between 0 and 100, with lower numbers
being displayed first. Actions should be between 10 and 30, with 20 being the
"go to cfp" action. General statistics start at 50.
The tile dictionary may optionally also contain a ``left`` or ``right`` key, which
should contain a dictionary with the keys ``text`` and optionally ``url`` and
``color``. The ``text`` key will be displayed as a button on the left or right side
of the tile, the optional ``url`` key will make the button clickable, and the
``color`` key should be one of ``success``, `info``, ``error`` or ``secondary``.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""
