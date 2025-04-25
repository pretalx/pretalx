from pretalx.common.signals import EventPluginSignal

submission_state_change = EventPluginSignal()
"""
This signal allows you to trigger additional events when a submission changes
its state. You will receive the submission after it has been saved, the previous
state, and the user triggering the change if available.
Any exceptions raised will be ignored.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, you will receive the keyword arguments ``submission``, ``old_state``,
and ``user`` (which may be ``None``).
When the submission is created or submitted from a draft state, ``old_state`` will be
``None``.
"""

submission_form_html = EventPluginSignal()
"""
This signal is sent out to display additional information on the submission
pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``submission`` which is currently displayed.
The receivers are expected to return HTML.
"""

submission_form_link = EventPluginSignal()
"""
This signal is sent out to display additional information on the submission
pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``submission`` which is currently displayed.
The receivers are expected to return HTML.
"""

submission_forms = EventPluginSignal()
"""
This signal is sent out to inject additional form fields on the submission
pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``submission`` which is currently displayed.
The receivers are expected to return one or more forms.
"""

review_form_html = EventPluginSignal()
"""
This signal is sent out to display additional information on the review tab
of the submission pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``submission`` which is currently displayed.
The receivers are expected to return HTML.
"""

review_forms = EventPluginSignal()
"""
This signal is sent out to inject additional form fields on the review tab
of the submission pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``submission`` which is currently displayed.
The receivers are expected to return one or more forms.
"""
