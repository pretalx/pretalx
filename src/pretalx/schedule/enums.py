# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.translation import gettext_lazy as _


class SlotType(models.TextChoices):
    BREAK = "break", _("Break")
    BLOCKER = "blocker", _("Blocker")
