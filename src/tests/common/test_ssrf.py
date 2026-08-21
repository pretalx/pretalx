# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import socket
from unittest import mock

import pytest
import requests
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError,
    HTTPError,
    LocationParseError,
    NameResolutionError,
    NewConnectionError,
)

from pretalx.common.ssrf import create_connection, should_block_access

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("ip", "reason"),
    (
        ("224.0.0.1", "multicast"),
        ("ff00::1", "multicast"),
        ("127.1.1.1", "local"),
        ("::1", "local"),
        ("fe80::1", "local"),
        ("0.0.0.0", "private"),
        ("10.0.0.3", "private"),
        ("192.168.5.3", "private"),
        ("fc00::1", "private"),
        ("100.100.100.100", "RFC 6598"),
        ("::ffff:100.64.0.1", "RFC 6598"),
    ),
)
def test_should_block_access_blocks_non_public(ip, reason):
    assert should_block_access((ip, 443)) == (
        True,
        f"Request to {reason} address {ip} blocked",
    )


@pytest.mark.parametrize("ip", ("8.8.8.8", "9.9.9.9", "2001:4860:4860::8888"))
def test_should_block_access_allows_public(ip):
    assert should_block_access((ip, 443)) == (False, None)


PRIVATE_IPS_RES = [
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.3", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.1.1.1", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("224.0.0.1", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.100.100.100", 443))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:100.64.0.1", 443, 0, 0))],
]

PUBLIC_RES = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]


@pytest.mark.parametrize("res", PRIVATE_IPS_RES)
@pytest.mark.parametrize("scheme", ("http", "https"))
def test_requests_to_rebound_private_address_blocked(res, scheme):
    with (
        mock.patch("socket.getaddrinfo", return_value=res),
        pytest.raises(
            HTTPError, match="Request to (multicast|private|local|RFC 6598) address.*"
        ),
    ):
        requests.get(f"{scheme}://example.org", timeout=0.1)


def test_requests_to_public_address_allowed():
    class SocketCreatedError(Exception):
        pass

    with (
        mock.patch("socket.getaddrinfo", return_value=PUBLIC_RES),
        mock.patch("socket.socket", side_effect=SocketCreatedError),
        pytest.raises(SocketCreatedError),
    ):
        requests.get("https://example.org", timeout=0.1)


def test_create_connection_connects_to_validated_address():
    with (
        mock.patch("socket.getaddrinfo", return_value=PUBLIC_RES),
        mock.patch("socket.socket") as mock_socket,
    ):
        sock = create_connection(("example.org", 80))

    assert sock is mock_socket.return_value
    mock_socket.return_value.connect.assert_called_once_with(("8.8.8.8", 80))
    mock_socket.return_value.settimeout.assert_not_called()
    mock_socket.return_value.bind.assert_not_called()


def test_new_conn_applies_timeout_and_source_address():
    conn = HTTPConnectionPool.ConnectionCls(
        "example.org", 80, timeout=3, source_address=("192.0.2.1", 0)
    )
    with (
        mock.patch("socket.getaddrinfo", return_value=PUBLIC_RES),
        mock.patch("socket.socket") as mock_socket,
    ):
        sock = conn._new_conn()

    assert sock is mock_socket.return_value
    mock_socket.return_value.settimeout.assert_called_once_with(3)
    mock_socket.return_value.bind.assert_called_once_with(("192.0.2.1", 0))


def test_new_conn_strips_ipv6_brackets_before_resolving():
    conn = HTTPConnectionPool.ConnectionCls("example.org", 80)
    conn.host = "[::1]"
    with (
        mock.patch(
            "socket.getaddrinfo",
            return_value=[
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 80, 0, 0))
            ],
        ) as mock_gai,
        pytest.raises(HTTPError, match="Request to local address ::1 blocked"),
    ):
        conn._new_conn()

    assert mock_gai.call_args[0][0] == "::1"


def test_new_conn_rejects_overlong_host_label():
    conn = HTTPConnectionPool.ConnectionCls("example.org", 80)
    conn.host = "a" * 64
    with pytest.raises(LocationParseError, match="label empty or too long"):
        conn._new_conn()


def test_new_conn_wraps_resolution_failure():
    conn = HTTPConnectionPool.ConnectionCls("example.org", 80)
    with (
        mock.patch("socket.getaddrinfo", side_effect=socket.gaierror),
        pytest.raises(NameResolutionError),
    ):
        conn._new_conn()


@pytest.mark.parametrize(
    ("connect_error", "expected_exc", "match"),
    (
        (socket.timeout, ConnectTimeoutError, None),
        (OSError("connection refused"), NewConnectionError, "connection refused"),
    ),
    ids=("timeout", "connect_error"),
)
def test_new_conn_wraps_connect_failure(connect_error, expected_exc, match):
    conn = HTTPConnectionPool.ConnectionCls("example.org", 80)
    with (
        mock.patch("socket.getaddrinfo", return_value=PUBLIC_RES),
        mock.patch("socket.socket") as mock_socket,
    ):
        mock_socket.return_value.connect.side_effect = connect_error
        with pytest.raises(expected_exc, match=match):
            conn._new_conn()

    mock_socket.return_value.close.assert_called_once_with()


def test_create_connection_socket_creation_failure():
    with (
        mock.patch("socket.getaddrinfo", return_value=PUBLIC_RES),
        mock.patch("socket.socket", side_effect=OSError("out of file descriptors")),
        pytest.raises(OSError, match="out of file descriptors"),
    ):
        create_connection(("example.org", 80))


def test_new_conn_empty_resolution_result():
    conn = HTTPConnectionPool.ConnectionCls("example.org", 80)
    with (
        mock.patch("socket.getaddrinfo", return_value=[]),
        pytest.raises(NewConnectionError, match="empty list"),
    ):
        conn._new_conn()
