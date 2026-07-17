"""Development-only screenshot corpus preparation tests."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from ceo_voice.api import create_app
from ceo_voice.config import (
    ApiSettings,
    ApplicationSettings,
    LoggingSettings,
    ModelSettings,
    Settings,
)
from ceo_voice.core.constants import Environment, LogFormat
from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.services import load_published_profile_catalog
from ceo_voice.showcase.manual_capture import (
    load_manual_capture_manifest,
    publish_manual_capture_bundle,
)

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _capture(
    number: int,
    *,
    complete: bool = True,
    quote: bool = False,
    repost: bool = False,
    quoted_content: bool | None = None,
    leader_name: str = "Ali Ghodsi",
    slug: str = "ali-ghodsi",
    platform: str = "linkedin",
) -> dict[str, object]:
    return {
        "capture_id": f"manual-{slug}-{platform}-{number:04d}",
        "leader_name": leader_name,
        "platform": platform,
        "content": f"Post {number}: explain the mechanism, show the result, and thank the team.",
        "visible_date": "1yr",
        "content_type": "post",
        "is_complete": complete,
        "is_repost": repost,
        "is_quote_post": quote,
        "quoted_content": (
            "Text written by another author."
            if (quote if quoted_content is None else quoted_content)
            else None
        ),
        "uncertain_spans": [],
        "capture_notes": None,
    }


def _write(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(records), encoding="utf-8")


def test_loader_excludes_incomplete_and_quoted_material_but_keeps_repost_commentary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "captures.json"
    records = [
        _capture(
            number,
            quote=number == 4,
            repost=number == 5,
            quoted_content=True if number == 5 else None,
            platform="x" if number == 6 else "linkedin",
        )
        for number in range(1, 21)
    ]
    records.append(_capture(21, complete=False))
    _write(path, records)

    manifest = load_manual_capture_manifest(
        profile_slug="ali-ghodsi",
        capture_paths=(path,),
        requested_at=NOW,
    )

    assert len(manifest.corpus.documents) == 20
    assert all(item.document.publication_date is None for item in manifest.corpus.documents)
    assert all(item.document.url is None for item in manifest.corpus.documents)
    quote = next(
        item.document
        for item in manifest.corpus.documents
        if item.document.external_id.endswith("0004")
    )
    assert "another author" not in quote.content
    assert quote.metadata["quoted_content_excluded"] is True
    repost = next(
        item.document
        for item in manifest.corpus.documents
        if item.document.external_id.endswith("0005")
    )
    assert repost.metadata["is_repost"] is True
    assert repost.metadata["quoted_content_excluded"] is True
    assert "repost-commentary" in repost.tags
    x_post = next(
        item.document
        for item in manifest.corpus.documents
        if item.document.external_id.endswith("0006")
    )
    assert x_post.platform is not None
    assert x_post.platform.value == "x"
    assert x_post.source.value == "x"
    assert x_post.metadata["content_type"] == "post"
    assert "post" in x_post.tags
    assert all(
        item.document.metadata["development_only"] is True for item in manifest.corpus.documents
    )


def test_loader_rejects_small_or_duplicate_corpora(tmp_path: Path) -> None:
    too_small = tmp_path / "small.json"
    _write(too_small, [_capture(number) for number in range(1, 20)])
    with pytest.raises(ValueError, match="at least 20"):
        load_manual_capture_manifest(
            profile_slug="ali-ghodsi", capture_paths=(too_small,), requested_at=NOW
        )

    duplicate = tmp_path / "duplicate.json"
    records = [_capture(number) for number in range(1, 21)]
    records.append(_capture(1))
    _write(duplicate, records)
    with pytest.raises(ValueError, match="must be unique"):
        load_manual_capture_manifest(
            profile_slug="ali-ghodsi", capture_paths=(duplicate,), requested_at=NOW
        )


def test_complete_capture_builds_self_validating_development_catalog(tmp_path: Path) -> None:
    capture = tmp_path / "captures.json"
    _write(capture, [_capture(number) for number in range(1, 21)])
    catalog = tmp_path / "published" / "catalog.json"

    bundle = asyncio.run(
        publish_manual_capture_bundle(
            profile_slug="ali-ghodsi",
            capture_paths=(capture,),
            workspace_root=tmp_path / "workspace",
            catalog_path=catalog,
        )
    )
    loaded = load_published_profile_catalog(catalog)

    assert bundle.artifact_status == "development"
    assert bundle.voice_profile.corpus_health.generation_ready is True
    assert len(bundle.voice_corpus.documents) == 20
    assert loaded == (bundle,)

    matei_capture = tmp_path / "matei-captures.json"
    _write(
        matei_capture,
        [
            _capture(
                number,
                leader_name="Matei Zaharia",
                slug="matei-zaharia",
            )
            for number in range(1, 21)
        ],
    )
    matei = asyncio.run(
        publish_manual_capture_bundle(
            profile_slug="matei-zaharia",
            capture_paths=(matei_capture,),
            workspace_root=tmp_path / "matei-workspace",
            catalog_path=catalog,
        )
    )
    assert {item.slug for item in load_published_profile_catalog(catalog)} == {
        bundle.slug,
        matei.slug,
    }

    production = Settings(
        _env_file=None,
        application=ApplicationSettings(environment=Environment.PRODUCTION),
        logging=LoggingSettings(format=LogFormat.JSON),
        api=ApiSettings(published_profile_catalog=catalog),
        model=ModelSettings(
            enabled=True,
            provider="gemini",
            generation_model="test-model",
            api_key=SecretStr("test-key"),
        ),
    )
    with pytest.raises(ConfigurationError, match="forbidden in production"):
        create_app(production)
