# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.signals import EventPluginSignal

schedule_release = EventPluginSignal()
"""
This signal allows you to trigger additional events when a new schedule
version is released. You will receive the new schedule and the user triggering
the change (if any).
Any exceptions raised will be ignored.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, you will receive the keyword arguments ``schedule``
and ``user`` (which may be ``None``).
"""
