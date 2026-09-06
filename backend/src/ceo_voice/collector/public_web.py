"""Research-only public article capture with source-faithful metadata.

This command does not create social posts, approve a source, or publish a voice profile.
Missing authorship/date/permission evidence remains missing in its JSON output.
"""

import argparse
import hashlib
import http.client
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

from ceo_voice.collector.public_http import PublicFetchError, PublicResponse, PublicWebFetcher


class ArticleParser(HTMLParser):
    """Extract one explicitly marked article body without executing HTML or scripts."""

    _VOID: ClassVar[set[str]] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
    _EXCLUDE: ClassVar[set[str]] = {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "form",
        "noscript",
    }

    def __init__(self, content_class: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.content_class = content_class
        self.stack: list[str] = []
        self.body_depth: int | None = None
        self.fragments: list[str] = []
        self.metadata: dict[str, str] = {}
        self.container_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if (
                key
                and content
                and key.lower()
                in {
                    "author",
                    "article:author",
                    "article:published_time",
                    "date",
                    "datepublished",
                    "og:title",
                    "og:site_name",
                    "og:url",
                }
            ):
                self.metadata[key.lower()] = content
        if tag == "time" and attributes.get("datetime"):
            self.metadata.setdefault("time:datetime", str(attributes["datetime"]))
        if "posthaven-formatted-date" in (attributes.get("class") or "").split() and attributes.get(
            "data-unix-time"
        ):
            self.metadata.setdefault("posthaven:data-unix-time", str(attributes["data-unix-time"]))
        if tag == "br" and self.body_depth is not None:
            self.fragments.append("\n")
        if tag in self._VOID:
            return
        self.stack.append(tag)
        matches = (
            self.content_class in (attributes.get("class") or "").split()
            if self.content_class
            else tag == "article"
        )
        if matches:
            self.container_count += 1
            if self.body_depth is None:
                self.body_depth = len(self.stack)
        if self.body_depth is not None and tag in {
            "p",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "blockquote",
        }:
            self.fragments.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.stack:
            return
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        if self.body_depth is not None and index < self.body_depth:
            self.body_depth = None
        self.stack = self.stack[:index]
        if tag in {"p", "div", "li", "blockquote"}:
            self.fragments.append("\n")

    def handle_data(self, data: str) -> None:
        if self.body_depth is not None and not any(tag in self._EXCLUDE for tag in self.stack):
            self.fragments.append(data)

    def text(self) -> str:
        if self.container_count != 1:
            raise PublicFetchError("exactly_one_article_container_required")
        paragraphs = [" ".join(line.split()) for line in "".join(self.fragments).splitlines()]
        value = "\n\n".join(line for line in paragraphs if line)
        if len(value.split()) < 40:
            raise PublicFetchError("article_body_too_short")
        return value


def extract_article(
    response: PublicResponse, content_class: str | None
) -> tuple[str, dict[str, str]]:
    """Decode bounded HTML or plain text; preserve raw bytes separately."""

    content_type = response.headers.get("content-type", "").lower()
    charset = "utf-8"
    for item in content_type.split(";")[1:]:
        if item.strip().startswith("charset="):
            charset = item.split("=", 1)[1].strip().strip('"')
    text = response.body.decode(charset, errors="strict")
    if content_type.split(";", 1)[0] == "text/plain":
        if len(text.split()) < 40:
            raise PublicFetchError("article_body_too_short")
        return text, {}
    if content_type.split(";", 1)[0] not in {"text/html", "application/xhtml+xml"}:
        raise PublicFetchError("unsupported_content_type")
    parser = ArticleParser(content_class)
    parser.feed(text)
    parser.close()
    return parser.text(), parser.metadata


def capture(
    fetcher: PublicWebFetcher,
    url: str,
    leader_slug: str,
    leader_name: str,
    output: Path,
    content_class: str | None = None,
) -> Path:
    """Save immutable raw source and research metadata in an operator-selected directory."""

    response, redirects = fetcher.fetch(url)
    content, metadata = extract_article(response, content_class)
    raw_hash = hashlib.sha256(response.body).hexdigest()
    identifier = hashlib.sha256(response.url.encode()).hexdigest()[:12] + "-" + raw_hash[:12]
    directory = output / identifier
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / "source.bin"
    raw_path.write_bytes(response.body)
    parsed = urlsplit(response.url)
    robots = fetcher.robots[f"https://{parsed.netloc}"][1]
    (directory / "robots.txt").write_bytes(robots.body)
    record = {
        "schema_version": "1.0",
        "artifact_status": "research_capture",
        "leader_slug": leader_slug,
        "leader_name_supplied": leader_name,
        "requested_url": url,
        "canonical_url": response.url,
        "redirect_chain": redirects,
        "acquisition_method": "public_web",
        "acquired_at": datetime.now(UTC).isoformat(),
        "source_modality": "authored_article_candidate",
        "platform": "generic",
        "content_role": "supplementary_voice",
        "observed_byline": metadata.get("author") or metadata.get("article:author"),
        "observed_publication_date": metadata.get("article:published_time")
        or metadata.get("datepublished")
        or metadata.get("date")
        or metadata.get("time:datetime"),
        "metadata_observed": metadata,
        "body_selector": {"class": content_class} if content_class else {"tag": "article"},
        "content": content,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "raw_sha256": raw_hash,
        "raw_path": raw_path.name,
        "http_status": response.status,
        "content_type": response.headers.get("content-type"),
        "robots_url": robots.url,
        "robots_http_status": robots.status,
        "robots_sha256": hashlib.sha256(robots.body).hexdigest(),
        "reuse_permission_basis": "unknown",
        "authorship_review": "pending",
        "eligible_for_generation": False,
        "performance": None,
        "limitations": [
            "Public availability and robots permission are not reuse permission.",
            "Supplied leader identity requires independent authorship review.",
            "An article is supplementary material, not evidence of X or LinkedIn formatting.",
            "Missing observed byline/publication date and engagement remain unknown.",
        ],
    }
    destination = directory / "capture.json"
    # Keep the first observed acquisition time for an identical immutable source version.
    if not destination.exists():
        destination.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--leader-slug", required=True)
    parser.add_argument("--leader-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--content-class")
    args = parser.parse_args(argv)
    try:
        path = capture(
            PublicWebFetcher(),
            args.url,
            args.leader_slug,
            args.leader_name,
            args.output,
            args.content_class,
        )
    except (ValueError, OSError, LookupError, http.client.HTTPException) as exc:
        print(json.dumps({"status": "blocked", "error": type(exc).__name__, "reason": str(exc)}))
        return 3
    print(json.dumps({"status": "captured_for_research", "path": str(path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
