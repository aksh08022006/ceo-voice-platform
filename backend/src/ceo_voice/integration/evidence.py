"""Resolve exact HVM and VKR spans from the corpora used by one integration run."""

from ceo_voice.profiles import CuratedCorpus, PublishedVoiceProfile
from ceo_voice.retrieval import EvidenceMaterial
from ceo_voice.retrieval.enums import EvidenceSourceKind
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.virality import ViralityCorpus
from ceo_voice.virality.contracts import CorpusAnalysis


def materialize_evidence(
    profile: PublishedVoiceProfile,
    profile_corpus: CuratedCorpus,
    analysis: CorpusAnalysis,
    virality_corpus: ViralityCorpus,
) -> tuple[EvidenceMaterial, ...]:
    """Materialize only content-addressed spans exposed by published artifacts."""

    profile_documents = {item.document.id: item.document for item in profile_corpus.documents}
    virality_documents = {item.document.id: item.document for item in virality_corpus.items}
    materials: list[EvidenceMaterial] = []
    for unit in profile.evidence_units:
        document = profile_documents[unit.document_id]
        content = document.content[unit.start_offset : unit.end_offset]
        if sha256_text(content) != unit.span_checksum:
            raise ValueError("HVM evidence span checksum mismatch")
        materials.append(
            EvidenceMaterial(
                evidence_id=unit.id,
                tenant_id=unit.tenant_id,
                document_id=unit.document_id,
                document_version=unit.document_version,
                content=content,
                content_hash=sha256_text(content),
                source_kind=EvidenceSourceKind.HVM,
                platform=unit.platform,
                publication_time=unit.publication_time,
                diversity_cluster_id=f"hvm:{unit.document_id}",
            )
        )
    for span in analysis.evidence:
        document = virality_documents[span.document_id]
        content = document.content[span.start : span.end]
        if sha256_text(content) != span.text_hash:
            raise ValueError("VKR evidence span checksum mismatch")
        materials.append(
            EvidenceMaterial(
                evidence_id=span.id,
                tenant_id=span.tenant_id,
                document_id=span.document_id,
                document_version=span.document_version,
                content=content,
                content_hash=sha256_text(content),
                source_kind=EvidenceSourceKind.VKR,
                platform=document.platform,
                publication_time=document.publication_date,
                diversity_cluster_id=f"vkr:{span.document_id}",
            )
        )
    return tuple(materials)
