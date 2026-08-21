# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import logging
import smtplib
import socket
from smtplib import SMTPSenderRefused

from django.core.mail.backends.smtp import EmailBackend

from pretalx.common.ssrf import should_block_access

logger = logging.getLogger(__name__)


def create_connection(
    address,
    timeout=socket._GLOBAL_DEFAULT_TIMEOUT,  # noqa: SLF001 -- stdlib sentinel
    source_address=None,
    *,
    all_errors=False,
):
    # Copied from socket.create_connection in the stdlib, with a
    # should_block_access() check on each resolved address. Resolving and
    # connecting in one place means the checked address is the one we connect
    # to, so a rebinding DNS server cannot swap it between check and use.

    host, port = address
    exceptions = []
    for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, socktype, proto, _canonname, sa = res

        is_private, msg = should_block_access(sa)
        if is_private:
            raise OSError(msg)

        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:  # noqa: SLF001 -- stdlib sentinel
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            # Break explicitly a reference cycle
            exceptions.clear()
            return sock  # noqa: TRY300 -- copied from stdlib

        except OSError as exc:
            if not all_errors:
                exceptions.clear()  # raise only the last error
            exceptions.append(exc)
            if sock is not None:
                sock.close()

    if exceptions:
        try:
            if not all_errors:
                raise exceptions[0]
            raise ExceptionGroup("create_connection failed", exceptions)
        finally:
            # Break explicitly a reference cycle
            exceptions.clear()
    else:
        raise OSError("getaddrinfo returns an empty list")


class CheckPrivateNetworkMixin:
    # _get_socket copied from smtplib, only calling our create_connection.
    def _get_socket(self, host, port, timeout):
        # This makes it simpler for SMTP_SSL to use the SMTP connect code
        # and just alter the socket connection bit.
        if timeout is not None and not timeout:
            raise ValueError("Non-blocking socket (timeout=0) is not supported")
        if self.debuglevel > 0:
            self._print_debug("connect: to", (host, port), self.source_address)
        return create_connection((host, port), timeout, self.source_address)


class SMTP(CheckPrivateNetworkMixin, smtplib.SMTP):
    pass


# smtplib.SMTP_SSL._get_socket calls super()._get_socket and wraps the result;
# the MRO below makes that super() resolve to our override on SMTP.
class SMTP_SSL(smtplib.SMTP_SSL, SMTP):  # noqa: N801
    pass


class CustomSMTPBackend(EmailBackend):
    @property
    def connection_class(self):
        return SMTP_SSL if self.use_ssl else SMTP

    def test(self, from_addr):
        try:
            self.open()
            self.connection.ehlo_or_helo_if_needed()
            code, resp = self.connection.mail(from_addr, [])
            if code != 250:
                logger.warning(
                    "Error testing mail settings, code %s, resp: %s", code, resp
                )
                raise SMTPSenderRefused(code, resp, sender=from_addr)
            code, resp = self.connection.rcpt("testdummy@pretalx.com")
            if code not in (250, 251):
                logger.warning(
                    "Error testing mail settings, code %s, resp: %s", code, resp
                )
                raise SMTPSenderRefused(code, resp, sender=from_addr)
        finally:
            self.close()
