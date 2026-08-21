# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import ipaddress
import socket
import sys

from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError,
    HTTPError,
    LocationParseError,
    NameResolutionError,
    NewConnectionError,
)
from urllib3.util.connection import (
    _TYPE_SOCKET_OPTIONS,
    _set_socket_options,
    allowed_gai_family,
)
from urllib3.util.timeout import _DEFAULT_TIMEOUT

CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


def should_block_access(sa):
    # Decide for a resolved socket address tuple whether connecting to it
    # would reach a non-public network. Returns (blocked, reason).
    ip_addr = ipaddress.ip_address(sa[0])
    check_ip4 = (
        ip_addr.ipv4_mapped if getattr(ip_addr, "ipv4_mapped", None) else ip_addr
    )
    if ip_addr.is_multicast:
        return True, f"Request to multicast address {sa[0]} blocked"
    if ip_addr.is_loopback or ip_addr.is_link_local:
        return True, f"Request to local address {sa[0]} blocked"
    if ip_addr.is_private:
        return True, f"Request to private address {sa[0]} blocked"
    if check_ip4 in CGNAT_NET:
        return True, f"Request to RFC 6598 address {sa[0]} blocked"

    return False, None


def create_connection(
    address: tuple[str, int],
    timeout=_DEFAULT_TIMEOUT,
    source_address: tuple[str, int] | None = None,
    socket_options: _TYPE_SOCKET_OPTIONS | None = None,
) -> socket.socket:
    # Copied from urllib3.util.connection (v2.7.0), plus the
    # should_block_access() check on each resolved address.
    host, port = address
    if host.startswith("["):
        host = host.strip("[]")
    err = None

    # Using the value from allowed_gai_family() in the context of getaddrinfo lets
    # us select whether to work with IPv4 DNS records, IPv6 records, or both.
    # The original create_connection function always returns all records.
    family = allowed_gai_family()

    try:
        host.encode("idna")
    except UnicodeError:
        raise LocationParseError(f"'{host}', label empty or too long") from None

    for res in socket.getaddrinfo(host, port, family, socket.SOCK_STREAM):
        af, socktype, proto, _canonname, sa = res

        is_private, msg = should_block_access(sa)
        if is_private:
            raise HTTPError(msg)

        sock = None
        try:
            sock = socket.socket(af, socktype, proto)

            # If provided, set socket level options before connecting.
            _set_socket_options(sock, socket_options)

            if timeout is not _DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            # Break explicitly a reference cycle
            err = None
            return sock  # noqa: TRY300 -- copied from urllib3

        except OSError as _:
            err = _
            if sock is not None:
                sock.close()

    if err is not None:
        try:
            raise err
        finally:
            # Break explicitly a reference cycle
            err = None
    else:
        raise OSError("getaddrinfo returns an empty list")


class ProtectionMixin:
    def _new_conn(self) -> socket.socket:
        # Copied from urllib3.connection.HTTPConnection._new_conn (v2.7.0),
        # only calling our create_connection instead.
        try:
            sock = create_connection(
                (self._dns_host, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as e:
            raise NameResolutionError(self.host, self, e) from e
        except TimeoutError as e:
            raise ConnectTimeoutError(
                self,
                f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
            ) from e

        except OSError as e:
            raise NewConnectionError(
                self, f"Failed to establish a new connection: {e}"
            ) from e

        sys.audit("http.client.connect", self, self.host, self.port)
        return sock


class ProtectedHTTPConnection(ProtectionMixin, HTTPConnection):
    pass


class ProtectedHTTPSConnection(ProtectionMixin, HTTPSConnection):
    pass


def monkeypatch_urllib3_ssrf_protection():
    """Guard urllib3 against SSRF into private networks.

    Currently mostly useful for plugins, but also future-safety."""
    HTTPConnectionPool.ConnectionCls = ProtectedHTTPConnection
    HTTPSConnectionPool.ConnectionCls = ProtectedHTTPSConnection
