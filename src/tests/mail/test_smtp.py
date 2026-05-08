# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import socket
from contextlib import contextmanager
from smtplib import SMTPSenderRefused
from unittest.mock import MagicMock, patch

import pytest

from pretalx.mail.smtp import CustomSMTPBackend

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("rcpt_code", (250, 251))
def test_custom_smtp_backend_test_success(rcpt_code):
    """rcpt code 251 (will forward) is also accepted."""
    backend = CustomSMTPBackend(host="localhost", port=25)
    mock_conn = MagicMock()
    mock_conn.mail.return_value = (250, b"OK")
    mock_conn.rcpt.return_value = (rcpt_code, b"OK")

    # Mocking open/close: this method talks directly to an SMTP server,
    # which is unavailable in tests (system boundary).
    with patch.object(backend, "open"), patch.object(backend, "close"):
        backend.connection = mock_conn
        backend.test("sender@test.org")


@pytest.mark.parametrize(
    ("mail_response", "rcpt_response"),
    (((550, b"Rejected"), (250, b"OK")), ((250, b"OK"), (550, b"Rejected"))),
)
def test_custom_smtp_backend_test_rejected(mail_response, rcpt_response):
    backend = CustomSMTPBackend(host="localhost", port=25)
    mock_conn = MagicMock()
    mock_conn.mail.return_value = mail_response
    mock_conn.rcpt.return_value = rcpt_response

    # Mocking open/close: SMTP server unavailable in tests (system boundary).
    with patch.object(backend, "open"), patch.object(backend, "close"):
        backend.connection = mock_conn
        with pytest.raises(SMTPSenderRefused) as exc_info:
            backend.test("sender@test.org")

    assert exc_info.value.smtp_code == 550


def test_custom_smtp_backend_test_closes_on_error():
    backend = CustomSMTPBackend(host="localhost", port=25)
    mock_conn = MagicMock()
    mock_conn.mail.return_value = (550, b"Rejected")

    # Mocking open/close: SMTP server unavailable in tests (system boundary).
    # We track close() to verify cleanup happens in the finally block.
    with patch.object(backend, "open"):
        backend.connection = mock_conn
        with pytest.raises(SMTPSenderRefused):
            backend.test("sender@test.org")

    # close() is a real method on the backend — verify it set connection to None
    assert backend.connection is None


# One getaddrinfo result per private/local/multicast/link-local address class.
# Ported verbatim from pretix PR #6073 (src/tests/base/test_mail.py).
PRIVATE_IPS_RES = [
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.3", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("0.0.0.0", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.1.1.1", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.5.3", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("224.0.0.1", 443))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("ff00::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fc00::1", 443, 0, 0))],
]


@contextmanager
def assert_mail_connection(res, should_connect, use_ssl):
    """Mock the SMTP socket/SSL plumbing and assert whether connect() ran."""
    with (
        patch("socket.socket") as mock_socket,
        patch("socket.getaddrinfo", return_value=res),
        patch("smtplib.SMTP.getreply", return_value=(220, b"")),
        patch("smtplib.SMTP.sendmail"),
        patch("ssl.SSLContext.wrap_socket") as mock_ssl,
    ):
        yield

        if should_connect:
            mock_socket.assert_called_once()
            mock_socket.return_value.connect.assert_called_once_with(res[0][-1])
            if use_ssl:
                mock_ssl.assert_called_once()
        else:
            mock_socket.assert_not_called()
            mock_socket.return_value.connect.assert_not_called()
            mock_ssl.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("res", PRIVATE_IPS_RES)
@pytest.mark.parametrize("use_ssl", (True, False))
def test_custom_smtp_backend_blocks_private_ip(res, use_ssl):
    with (
        assert_mail_connection(res=res, should_connect=False, use_ssl=use_ssl),
        pytest.raises(OSError, match="Request to .* blocked"),
    ):
        CustomSMTPBackend(host="smtp.example.com", use_ssl=use_ssl).open()


@pytest.mark.django_db
@pytest.mark.parametrize("use_ssl", (True, False))
def test_custom_smtp_backend_public_ip_allowed(use_ssl):
    public_res = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    with assert_mail_connection(res=public_res, should_connect=True, use_ssl=use_ssl):
        CustomSMTPBackend(host="smtp.example.com", use_ssl=use_ssl).open()
