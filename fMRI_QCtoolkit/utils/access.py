import hmac
import ipaddress
import secrets
import socket
from urllib.parse import urlencode

from flask import Flask, redirect, request

DENIED_MESSAGE = (
    "<h2>Access denied</h2>"
    "<p>Open the link printed in the terminal that started this server. "
    "Links stop working when the server restarts.</p>"
)


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def url_host(bind_host: str) -> str:
    """The host to put in a printed link: a wildcard bind gets this machine's name, IPv6 gets brackets."""
    bare = bind_host.strip("[]")
    if bare in ("", "0.0.0.0", "::"):
        return socket.gethostname()
    return f"[{bare}]" if ":" in bare else bare


def _split_host_header(value: str):
    """Host header -> (hostname, port), handling the bracketed IPv6 form."""
    if value.startswith("["):
        hostname, _, rest = value[1:].partition("]")
        return hostname.lower(), rest.lstrip(":")
    hostname, _, port = value.partition(":")
    return hostname.lower(), port


class AccessGate:
    """Session token check plus, on a loopback bind, a Host header check against DNS rebinding."""

    def __init__(self, server: Flask, token: str = None):
        self.token = token or secrets.token_urlsafe(32)
        self.bind_host = "127.0.0.1"
        server.before_request(self._check)

    def link(self, base_url: str, path: str = "/") -> str:
        return f"{base_url}{path}?{urlencode({'token': self.token})}"

    def _matches(self, supplied: str) -> bool:
        return hmac.compare_digest(supplied.encode(), self.token.encode())

    def _check(self):
        hostname, port = _split_host_header(request.host)
        if is_loopback(self.bind_host) and not is_loopback(hostname):
            return DENIED_MESSAGE, 403

        # Browsers share localhost cookies across ports, so key the cookie by the port they see
        cookie_name = f"qc_token_{port or 'default'}"

        supplied = request.args.get("token")
        if supplied is not None:
            if not self._matches(supplied):
                return DENIED_MESSAGE, 403
            args = request.args.copy()
            args.pop("token")
            query = urlencode(list(args.items(multi=True)))
            response = redirect(request.path + (f"?{query}" if query else ""))
            response.set_cookie(cookie_name, self.token, httponly=True, samesite="Lax")
            return response

        if not self._matches(request.cookies.get(cookie_name, "")):
            return DENIED_MESSAGE, 403
        return None
