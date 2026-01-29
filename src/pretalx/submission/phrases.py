# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import pgettext_lazy

from pretalx.common.text.phrases import Phrases


class SubmissionPhrases(Phrases, app="submission"):
    submitted = pgettext_lazy("proposal status", "submitted")
    in_review = pgettext_lazy("proposal status", "in review")
    not_accepted = pgettext_lazy("proposal status", "not accepted")
