"""Executable bridge from reviewed local exports to a profile-build manifest."""

from pathlib import Path
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.acquisition import CatalogAuthorizedConnector, SourceCatalogManifest
from ceo_voice.core.exceptions import DataIngestionError, StorageError
from ceo_voice.ingestion import (
    ConnectorRegistry,
    FetchRequest,
    IngestionPipeline,
    IngestionRepositories,
    IngestionRunResult,
    LocalExportConnector,
)
from ceo_voice.ingestion.repositories import (
    InMemoryCheckpointRepository,
    InMemoryCleanDocumentRepository,
    InMemoryMetadataRepository,
    InMemoryRawDocumentRepository,
)
from ceo_voice.models.base import ContractModel, UtcDatetime
from ceo_voice.models.enums import DocumentSourceType
from ceo_voice.profiles.contracts import CuratedCorpus, CuratedDocument, ProfileBuildManifest
from ceo_voice.voice import ProfileLineage, SourceModality, VoiceIdentity


class CorpusImportSource(ContractModel):
    """One reviewed export and the modality assigned to all admitted records."""

    source: DocumentSourceType
    export_path: Path
    modality: SourceModality
    limit: int = Field(default=1_000, ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if self.export_path.is_absolute() or ".." in self.export_path.parts:
            raise ValueError("export paths must be confined relative paths")
        if self.export_path.suffix.lower() not in {".json", ".jsonl"}:
            raise ValueError("exports must use .json or .jsonl")
        return self


class CorpusPreparationManifest(ContractModel):
    """All governed inputs required to prepare a build without hand-assembled documents."""

    catalog: SourceCatalogManifest
    identity: VoiceIdentity
    lineage: ProfileLineage
    sources: tuple[CorpusImportSource, ...] = Field(min_length=1)
    actor_id: UUID
    requested_at: UtcDatetime
    publish: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (
            self.catalog.tenant_id != self.identity.tenant_id
            or self.catalog.leader_id != self.identity.leader_id
        ):
            raise ValueError("catalog and identity must share tenant and leader scope")
        if self.catalog.leader_name.casefold() != self.identity.display_name.casefold():
            raise ValueError("catalog and identity names must match")
        if self.lineage.tenant_id != self.identity.tenant_id:
            raise ValueError("lineage and identity must share a tenant")
        if self.lineage.voice_identity_id != self.identity.id:
            raise ValueError("lineage must reference the prepared identity")
        source_types = tuple(item.source for item in self.sources)
        if len(source_types) != len(set(source_types)):
            raise ValueError("one export is allowed per source type in a preparation run")
        return self


class CorpusPreparationResult(ContractModel):
    """Profile command plus traceable ingestion outcomes for every source export."""

    profile_manifest: ProfileBuildManifest
    ingestion_runs: tuple[IngestionRunResult, ...] = Field(min_length=1)


class CorpusPreparationService:
    """Authorize, normalize, validate, and curate reviewed exports for profile construction."""

    def __init__(self, export_root: Path) -> None:
        self._root = export_root.expanduser().resolve()

    async def prepare(self, manifest: CorpusPreparationManifest) -> CorpusPreparationResult:
        """Run every export through the production pipeline and return admitted clean documents."""

        repositories = IngestionRepositories(
            raw_documents=InMemoryRawDocumentRepository(),
            clean_documents=InMemoryCleanDocumentRepository(),
            metadata=InMemoryMetadataRepository(),
            checkpoints=InMemoryCheckpointRepository(),
        )
        curated: list[CuratedDocument] = []
        runs: list[IngestionRunResult] = []
        for source in manifest.sources:
            connector = CatalogAuthorizedConnector(
                connector=LocalExportConnector(root=self._root, source_type=source.source),
                manifest=manifest.catalog,
            )
            pipeline = IngestionPipeline(
                connectors=ConnectorRegistry((connector,)), repositories=repositories
            )
            run = await pipeline.run(
                connector.connector_id,
                FetchRequest(
                    tenant_id=manifest.catalog.tenant_id,
                    ceo_id=manifest.catalog.leader_id,
                    limit=source.limit,
                    options={"path": source.export_path.as_posix()},
                ),
            )
            runs.append(run)
            for item in run.items:
                if item.document_id is None or item.document_version is None:
                    continue
                document = await repositories.clean_documents.get(
                    manifest.catalog.tenant_id, item.document_id, item.document_version
                )
                if document is None:
                    raise StorageError("stored ingestion document could not be projected")
                curated.append(CuratedDocument(document=document, source_modality=source.modality))
        if not curated:
            raise DataIngestionError("corpus preparation admitted no clean documents")
        command = ProfileBuildManifest(
            corpus=CuratedCorpus(
                identity=manifest.identity,
                lineage=manifest.lineage,
                documents=tuple(curated),
            ),
            actor_id=manifest.actor_id,
            requested_at=manifest.requested_at,
            publish=manifest.publish,
        )
        return CorpusPreparationResult(profile_manifest=command, ingestion_runs=tuple(runs))
