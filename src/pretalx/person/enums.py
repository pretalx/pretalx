# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.translation import gettext_lazy as _


class SpeakerProfileOrigin(models.TextChoices):
    CFP = "cfp", _("CfP")
    ORGA = "orga", _("Organiser")
    IMPORT = "import", _("Import")
