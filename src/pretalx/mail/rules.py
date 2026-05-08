# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import rules

from pretalx.mail.enums import QueuedMailStates


@rules.predicate
def can_edit_mail(user, obj):
    return getattr(obj, "state", None) == QueuedMailStates.DRAFT
