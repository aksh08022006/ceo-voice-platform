"""Deployment catalog confinement and diagnostics."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.services import (
    PublishedProfileCatalogManifest,
    load_published_profile_catalog,
)


@pytest.mark.parametrize("path", (Path("/absolute.json"), Path("../escape.json")))
def test_catalog_rejects_unconfined_paths(path: Path) -> None:
    with pytest.raises(ValidationError, match="confined relative"):
        PublishedProfileCatalogManifest(schema_version="1.0", bundles=(path,))


def test_catalog_rejects_duplicate_paths() -> None:
    with pytest.raises(ValidationError, match="unique"):
        PublishedProfileCatalogManifest(
            schema_version="1.0",
            bundles=(Path("profile.json"), Path("profile.json")),
        )


def test_missing_catalog_is_safe_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="catalog is invalid") as captured:
        load_published_profile_catalog(tmp_path / "missing.json")
    assert str(captured.value.details["catalog"]).endswith("missing.json")
