"""Allow only the stdlib socketpair operation, not arbitrary connections."""
from __future__ import annotations

import os
import socket

import pytest

from tests.conftest import NetworkBlockedError

pytestmark = pytest.mark.skipif(os.environ.get("MELODINE_TEST_ALLOW_NETWORK") == "1",
                               reason="network guard disabled explicitly")


def test_socketpair_operates_with_network_guard():
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"ok")
        assert right.recv(2) == b"ok"


@pytest.mark.parametrize("host", ["127.0.0.1", "192.0.2.1"])
@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_external_and_arbitrary_loopback_connections_are_blocked(host, method):
    with socket.socket() as sock, pytest.raises(NetworkBlockedError):
        getattr(sock, method)((host, 1))
