# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from .compose import WriteMailBaseForm, WriteSessionMailForm, WriteTeamsMailForm
from .config import ENCRYPTED_PASSWORD_PLACEHOLDER, MailSettingsForm
from .queued_mail import MailDetailForm, QueuedMailFilterForm
from .template import MailTemplateForm

__all__ = [
    "ENCRYPTED_PASSWORD_PLACEHOLDER",
    "MailDetailForm",
    "MailSettingsForm",
    "MailTemplateForm",
    "QueuedMailFilterForm",
    "WriteMailBaseForm",
    "WriteSessionMailForm",
    "WriteTeamsMailForm",
]
