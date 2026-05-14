# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import Signal

delete_user = Signal()
"""
This signal is sent out when a user is deleted - both when deleted on the
frontend ("deactivated") and actually removed ("shredded").

You will get the user as a keyword argument ``user``. Receivers are expected to
delete any personal information they might have stored about this user.

Additionally, you will get the keyword argument ``db_delete`` when the user
object will be deleted from the database. If you have any foreign keys to the
user object, you should delete them here.
"""
