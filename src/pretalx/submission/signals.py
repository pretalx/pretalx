# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.signals import EventPluginSignal

before_submission_state_change = EventPluginSignal()
"""
This signal is fired before a submission's state is changed, allowing plugins to
prevent the transition. Receivers get the submission (with its current state still
intact), the intended new state, and the user triggering the change.

This signal is **not** fired for the initial submission (draft/new to submitted),
only for subsequent state changes.

Raising :class:`~pretalx.common.exceptions.SubmissionError` will cancel the state
change. Any other exceptions are ignored.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, you will receive the keyword arguments ``submission``, ``new_state``,
and ``user`` (which may be ``None``).
"""

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
