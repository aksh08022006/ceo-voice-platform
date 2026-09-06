"""Public acquisition boundaries and source-faithful extraction regressions."""

import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import Mock

import pytest

from ceo_voice.collector import public_http, public_web
from ceo_voice.collector.public_http import (
    PublicFetchError,
    PublicResponse,
    PublicWebFetcher,
    public_addresses,
    request_once,
    validate_public_url,
)
from ceo_voice.collector.public_web import ArticleParser, capture, extract_article

ORIGIN = "https://writer.example"
WORDS = " ".join(f"word{index}" for index in range(50))


def response(
    url: str,
    status: int = 200,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    location: str | None = None,
) -> PublicResponse:
    default_type = "text/plain" if url.endswith("/robots.txt") else "text/html"
    values = {"content-type": default_type, **(headers or {})}
    if location is not None:
        values["location"] = location
    return PublicResponse(url, status, values, body, "93.184.216.34")


@pytest.mark.parametrize(
    "url",
    [
        "http://writer.example/a",
        "https://u:p@writer.example/a",
        "https://writer.example:444/a",
        "https:///missing",
        "https://writer.example/\nsecret",
        "https://[fe80::1%en0]/",
        "https://writer.example/article?accessToken=secret",
    ],
)
def test_rejects_nonanonymous_or_nonstandard_urls(url: str) -> None:
    with pytest.raises(PublicFetchError):
        validate_public_url(url)


def test_removes_fragment() -> None:
    assert validate_public_url(ORIGIN + "/article#fragment") == ORIGIN + "/article"


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.2.3.4",),
        ("169.254.169.254",),
        ("::1",),
        ("ff02::1",),
        ("93.184.216.34", "192.168.1.1"),
        (),
    ],
)
def test_rejects_private_mixed_or_missing_dns_answers(
    monkeypatch: pytest.MonkeyPatch, addresses: tuple[str, ...]
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443)) for value in addresses
        ],
    )
    with pytest.raises(PublicFetchError, match="non_public_address"):
        public_addresses("writer.example")


def test_request_pins_address_keeps_hostname_and_bounds_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    wire = Mock()
    wire.status = 200
    wire.getheaders.return_value = [("Content-Type", "text/html")]
    wire.read.return_value = b"body"
    connection = Mock()
    connection.getresponse.return_value = wire
    factory = Mock(return_value=connection)
    monkeypatch.setattr(public_http, "_PinnedHTTPSConnection", factory)
    result = request_once(ORIGIN + "/article?q=1", 20)
    assert result.body == b"body"
    factory.assert_called_once_with("writer.example", "93.184.216.34", timeout=15.0)
    assert connection.request.call_args.args == ("GET", "/article?q=1")
    assert "Cookie" not in connection.request.call_args.kwargs["headers"]
    wire.read.assert_called_once_with(21)
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "headers,body,error",
    [
        ({"Content-Encoding": "gzip"}, b"", "compressed_response"),
        ({"Content-Length": "21"}, b"", "response_too_large"),
        ({"Content-Length": "invalid"}, b"", "response_too_large"),
        ({}, b"x" * 21, "response_too_large"),
    ],
)
def test_transport_closes_on_rejected_responses(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], body: bytes, error: str
) -> None:
    monkeypatch.setattr(public_http, "public_addresses", lambda hostname: ("93.184.216.34",))
    wire = Mock()
    wire.getheaders.return_value = list(headers.items())
    wire.read.return_value = body
    connection = Mock()
    connection.getresponse.return_value = wire
    monkeypatch.setattr(public_http, "_PinnedHTTPSConnection", Mock(return_value=connection))
    with pytest.raises(PublicFetchError, match=error):
        request_once(ORIGIN, 20)
    connection.close.assert_called_once()


def test_tls_sni_uses_original_host_with_pinned_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    sock, tls = Mock(), Mock()
    connect = Mock(return_value=sock)
    monkeypatch.setattr(socket, "create_connection", connect)
    connection = public_http._PinnedHTTPSConnection("writer.example", "93.184.216.34", 10)
    connection.tls_context = tls
    connection.connect()
    connect.assert_called_once_with(("93.184.216.34", 443), 10)
    tls.wrap_socket.assert_called_once_with(sock, server_hostname="writer.example")


@pytest.mark.parametrize(
    "robots,status,error",
    [
        (b"User-agent: *\nDisallow: /article", 200, "robots_disallow"),
        (b"", 403, "robots_unavailable_http_403"),
        (b"", 302, "robots_unavailable_http_302"),
        (b"User-agent: *\nCrawl-delay: 31", 200, "robots_delay"),
    ],
)
def test_blocks_before_article_request(robots: bytes, status: int, error: str) -> None:
    request = Mock(return_value=response(ORIGIN + "/robots.txt", status, robots))
    with pytest.raises(PublicFetchError, match=error):
        PublicWebFetcher(request=request).fetch(ORIGIN + "/article")
    assert request.call_count == 1


def test_follows_public_redirect_and_honors_cached_robots_delay() -> None:
    request = Mock(
        side_effect=[
            response(
                ORIGIN + "/robots.txt", 200, b"User-agent: *\nCrawl-delay: 2\nRequest-rate: 1/3"
            ),
            response(ORIGIN + "/old", 302, location="/article"),
            response(ORIGIN + "/article", body=b"article"),
        ]
    )
    sleeps: list[float] = []
    fetcher = PublicWebFetcher(request=request, sleep=sleeps.append, clock=lambda: 10.0)
    result, redirects = fetcher.fetch(ORIGIN + "/old")
    assert result.body == b"article" and redirects == (ORIGIN + "/old",)
    assert sleeps == [3.0]


def test_robots_challenge_html_is_not_treated_as_permission() -> None:
    request = Mock(
        return_value=response(
            ORIGIN + "/robots.txt", body=b"Login required", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(PublicFetchError, match="robots_not_plain_text"):
        PublicWebFetcher(request=request).fetch(ORIGIN)
    assert request.call_count == 1


@pytest.mark.parametrize(
    "status,headers,error",
    [
        (401, {}, "public_page_http_401"),
        (302, {}, "redirect_missing_location"),
        (302, {"location": "http://writer.example/article"}, "anonymous_https"),
    ],
)
def test_public_denials_and_redirect_failures(
    status: int, headers: dict[str, str], error: str
) -> None:
    request = Mock(
        side_effect=[
            response(ORIGIN + "/robots.txt", 404),
            response(ORIGIN, status, headers=headers),
        ]
    )
    with pytest.raises(PublicFetchError, match=error):
        PublicWebFetcher(request=request).fetch(ORIGIN)


def test_redirect_limit() -> None:
    request = Mock(
        side_effect=[response(ORIGIN + "/robots.txt", 410)]
        + [response(ORIGIN, 302, location="/loop") for _ in range(4)]
    )
    with pytest.raises(PublicFetchError, match="too_many_redirects"):
        PublicWebFetcher(request=request, sleep=lambda delay: None, clock=lambda: 10).fetch(ORIGIN)


def test_extracts_selected_prose_and_retains_only_observed_metadata() -> None:
    html = f"""<html><head><meta property="og:title" content="Essay"><meta name="author" content="Writer"></head>
    <body><header>navigation</header><article><div class="post-body"><p>{WORDS}</p><br>
    <script>private_script</script><nav>related articles</nav><p>Final paragraph.</p></div></article>
    <time datetime="2025-01-02T12:00:00Z"></time>
    <span class="posthaven-formatted-date" data-unix-time="1735819200"></span></body></html>"""
    text, metadata = extract_article(response(ORIGIN, body=html.encode()), "post-body")
    assert "navigation" not in text and "private_script" not in text and "related" not in text
    assert "Final paragraph." in text and metadata["author"] == "Writer"
    assert metadata["time:datetime"] == "2025-01-02T12:00:00Z"
    assert metadata["posthaven:data-unix-time"] == "1735819200"


@pytest.mark.parametrize(
    "html",
    [
        "<p>Not an article</p>",
        "<article>short</article>",
        f"<article>{WORDS}</article><article>{WORDS}</article>",
    ],
)
def test_rejects_ambiguous_missing_or_trivial_bodies(html: str) -> None:
    with pytest.raises(PublicFetchError):
        extract_article(response(ORIGIN, body=html.encode()), None)


def test_plain_text_and_content_type_guards() -> None:
    text, metadata = extract_article(
        response(
            ORIGIN, body=WORDS.encode(), headers={"content-type": 'text/plain; charset="utf-8"'}
        ),
        None,
    )
    assert text == WORDS and metadata == {}
    with pytest.raises(PublicFetchError, match="unsupported_content_type"):
        extract_article(response(ORIGIN, headers={"content-type": "application/json"}), None)
    with pytest.raises(PublicFetchError, match="article_body_too_short"):
        extract_article(
            response(ORIGIN, body=b"short", headers={"content-type": "text/plain"}), None
        )
    parser = ArticleParser()
    parser.handle_endtag("missing")


def test_capture_is_supplementary_preserves_raw_and_never_fabricates_date(tmp_path: Path) -> None:
    raw = f"<article>{WORDS}</article>".encode()
    request = Mock(
        side_effect=[
            response(ORIGIN + "/robots.txt", 404),
            response(ORIGIN, body=raw),
            response(ORIGIN, body=raw),
        ]
    )
    fetcher = PublicWebFetcher(request=request, sleep=lambda delay: None, clock=lambda: 10)
    path = capture(fetcher, ORIGIN, "writer", "Writer", tmp_path)
    first = path.read_bytes()
    data = json.loads(first)
    assert data["observed_byline"] is None and data["observed_publication_date"] is None
    assert data["platform"] == "generic" and data["eligible_for_generation"] is False
    assert data["reuse_permission_basis"] == "unknown" and data["performance"] is None
    assert data["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert path.with_name("source.bin").read_bytes() == raw
    assert capture(fetcher, ORIGIN, "writer", "Writer", tmp_path) == path
    assert path.read_bytes() == first


def test_capture_cli_reports_success_and_explicit_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    args = [
        "--url",
        ORIGIN,
        "--leader-slug",
        "writer",
        "--leader-name",
        "Writer",
        "--output",
        str(tmp_path),
    ]
    monkeypatch.setattr(public_web, "capture", Mock(return_value=tmp_path / "capture.json"))
    assert public_web.main(args) == 0
    monkeypatch.setattr(
        public_web, "capture", Mock(side_effect=PublicFetchError("robots_disallow"))
    )
    assert public_web.main(args) == 3
