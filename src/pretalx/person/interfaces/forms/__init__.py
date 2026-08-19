# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from .auth import (
    EmailCorrectionForm,
    LoginInfoForm,
    RecoverForm,
    ResetForm,
    SpeakerLoginInfoForm,
    UserForm,
)
from .auth_token import AuthTokenForm
from .information import SpeakerInformationForm
from .invitation import SubmissionInvitationForm
from .profile import (
    OrgaProfileForm,
    SpeakerAvailabilityForm,
    SpeakerInviteForm,
    SpeakerMergeForm,
    SpeakerProfileForm,
)

__all__ = [
    "AuthTokenForm",
    "EmailCorrectionForm",
    "LoginInfoForm",
    "OrgaProfileForm",
    "RecoverForm",
    "ResetForm",
    "SpeakerAvailabilityForm",
    "SpeakerInformationForm",
    "SpeakerInviteForm",
    "SpeakerLoginInfoForm",
    "SpeakerMergeForm",
    "SpeakerProfileForm",
    "SubmissionInvitationForm",
    "UserForm",
]
