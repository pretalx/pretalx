# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import ipaddress
import logging
import smtplib
import socket
from smtplib import SMTPSenderRefused

from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


class SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
            ip = ipaddress.ip_address(res[4][0])
            if ip.is_multicast or ip.is_loopback or ip.is_link_local or ip.is_private:
                raise OSError(f"Request to address {ip} blocked")
        return super()._get_socket(host, port, timeout)


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
