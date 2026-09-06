"""Bounded anonymous HTTPS transport for explicit public research URLs.

DNS results are checked and the connection is pinned to a checked address. The original
hostname remains the TLS verification/SNI name and Host header. No browser credentials,
cookies, proxy environment variables, JavaScript, or authentication retries are used.
"""

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "CEO-Voice-Research/0.1"
MAX_PAGE_BYTES = 2_000_000
MAX_ROBOTS_BYTES = 256_000


class PublicFetchError(ValueError):
    """An explicit public acquisition failure; callers must not bypass it."""


@dataclass(frozen=True)
class PublicResponse:
    """Exact response bytes and the metadata used to acquire them."""

    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    peer_ip: str


def validate_public_url(url: str) -> str:
    """Require an anonymous standard-port HTTPS URL before resolving anything."""

    if any(ord(char) < 33 or ord(char) == 127 for char in url):
        raise PublicFetchError("invalid_url_characters")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or "%" in parsed.hostname
        or any(
            key.lower().replace("_", "").replace("-", "")
            in {
                "accesstoken",
                "token",
                "apikey",
                "authorization",
                "password",
                "signature",
                "xamzsignature",
            }
            for key, _ in parse_qsl(parsed.query)
        )
    ):
        raise PublicFetchError("anonymous_https_port_443_required")
    return parsed._replace(fragment="").geturl()


def public_addresses(hostname: str) -> tuple[str, ...]:
    """Reject a hostname if any DNS answer is non-public, including mixed answers."""

    addresses = tuple(
        dict.fromkeys(
            str(item[4][0]) for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        )
    )
    if not addresses or any(
        not ipaddress.ip_address(value).is_global
        or ipaddress.ip_address(value).is_multicast
        or ipaddress.ip_address(value).is_reserved
        for value in addresses
    ):
        raise PublicFetchError("non_public_address")
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float) -> None:
        self.tls_context = ssl.create_default_context()
        super().__init__(host, port=443, timeout=timeout, context=self.tls_context)
        self.address = address
        self.request_timeout = timeout

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, 443), self.request_timeout)
        self.sock = self.tls_context.wrap_socket(self.sock, server_hostname=self.host)


def request_once(url: str, maximum_bytes: int) -> PublicResponse:
    """Read one response without following redirects or decompressing unbounded data."""

    normalized = validate_public_url(url)
    parsed = urlsplit(normalized)
    assert parsed.hostname is not None
    hostname = parsed.hostname.encode("idna").decode("ascii")
    address = public_addresses(hostname)[0]
    connection = _PinnedHTTPSConnection(hostname, address, timeout=15.0)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request(
            "GET",
            path,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, text/plain;q=0.9",
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        if headers.get("content-encoding", "identity").lower() != "identity":
            raise PublicFetchError("compressed_response_unsupported")
        length = headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > maximum_bytes):
            raise PublicFetchError("response_too_large")
        body = response.read(maximum_bytes + 1)
        if len(body) > maximum_bytes:
            raise PublicFetchError("response_too_large")
        return PublicResponse(normalized, response.status, headers, body, address)
    finally:
        connection.close()


class PublicWebFetcher:
    """Fetch explicit pages only, checking robots and every redirect destination."""

    def __init__(
        self,
        request: Callable[[str, int], PublicResponse] = request_once,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.request = request
        self.sleep = sleep
        self.clock = clock
        self.robots: dict[str, tuple[RobotFileParser, PublicResponse]] = {}
        self.next_request: dict[str, float] = {}

    def _allow(self, url: str) -> None:
        parsed = urlsplit(url)
        origin = f"https://{parsed.netloc}"
        if origin not in self.robots:
            response = self.request(origin + "/robots.txt", MAX_ROBOTS_BYTES)
            parser = RobotFileParser(origin + "/robots.txt")
            if response.status in {404, 410}:
                parser.parse(["User-agent: *", "Disallow:"])
            elif response.status == 200:
                if (
                    response.headers.get("content-type", "").split(";", 1)[0].lower()
                    != "text/plain"
                ):
                    raise PublicFetchError("robots_not_plain_text")
                parser.parse(response.body.decode("utf-8", errors="strict").splitlines())
            else:
                # A redirect, denial, timeout, or service failure is not authorization.
                raise PublicFetchError(f"robots_unavailable_http_{response.status}")
            self.robots[origin] = (parser, response)
        parser, _ = self.robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise PublicFetchError("robots_disallow")
        rate = parser.request_rate(USER_AGENT)
        interval = max(
            1.0,
            float(parser.crawl_delay(USER_AGENT) or 0),
            rate.seconds / rate.requests if rate else 0.0,
        )
        if interval > 30:
            raise PublicFetchError("robots_delay_exceeds_interactive_limit")
        wait = self.next_request.get(origin, 0.0) - self.clock()
        if wait > 0:
            self.sleep(wait)
        self.next_request[origin] = self.clock() + interval

    def fetch(self, url: str) -> tuple[PublicResponse, tuple[str, ...]]:
        current = validate_public_url(url)
        redirects: list[str] = []
        for _ in range(4):
            self._allow(current)
            response = self.request(current, MAX_PAGE_BYTES)
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise PublicFetchError("redirect_missing_location")
                redirects.append(current)
                current = validate_public_url(urljoin(current, location))
                continue
            if response.status != 200:
                raise PublicFetchError(f"public_page_http_{response.status}")
            return response, tuple(redirects)
        raise PublicFetchError("too_many_redirects")
