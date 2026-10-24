import socket

import pytest
from flask import Flask
from werkzeug.serving import make_server

from fMRI_QCtoolkit.utils.port_utils import find_free_port


@pytest.fixture
def listening_port():
    # A real werkzeug server, which sets SO_REUSEADDR on its own socket
    server = make_server("127.0.0.1", 0, Flask(__name__))
    yield server.server_port
    server.server_close()


def test_port_with_a_listening_server_is_skipped(listening_port):
    assert find_free_port(start=listening_port, end=listening_port + 20, delay=0) != listening_port


def _has_ipv6_loopback():
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            sock.bind(("::1", 0))
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _has_ipv6_loopback(), reason="no IPv6 loopback")
def test_ipv6_host_is_probed_on_ipv6():
    assert find_free_port(start=5000, end=5500, delay=0, host="::1") in range(5000, 5500)


def test_unresolvable_host_is_a_clean_error():
    with pytest.raises(RuntimeError, match="Cannot resolve host"):
        find_free_port(start=5000, end=5001, delay=0, host="no-such-host.invalid")
