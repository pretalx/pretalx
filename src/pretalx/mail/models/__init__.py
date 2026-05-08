# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from .queued_mail import QueuedMail
from .templates import MailTemplate

__all__ = ["MailTemplate", "QueuedMail"]
