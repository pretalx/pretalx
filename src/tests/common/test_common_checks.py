# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.test import override_settings

from pretalx.common.checks import check_system_email

VALID_EMAIL_SETTINGS = {
    "EMAIL_HOST": "localhost",
    "EMAIL_PORT": 25,
    "EMAIL_USE_TLS": False,
    "EMAIL_USE_SSL": False,
}


@pytest.mark.parametrize(
    "mail_from",
    (
        "not-an-email",
        "Just A Name",
    ),
)
def test_check_system_email_invalid_mail_from(mail_from):
    with override_settings(**VALID_EMAIL_SETTINGS, MAIL_FROM=mail_from):
        errors = check_system_email(None)
        ids = [e.id for e in errors]
        assert "pretalx.E003" in ids


@pytest.mark.parametrize(
    "mail_from",
    (
        "orga@example.com",
        "Custom Sender <orga@example.com>",
    ),
)
def test_check_system_email_valid_mail_from(mail_from):
    with override_settings(**VALID_EMAIL_SETTINGS, MAIL_FROM=mail_from):
        errors = check_system_email(None)
        ids = [e.id for e in errors]
        assert "pretalx.E003" not in ids
