"""Validation and role partitioning for already-retrieved evidence."""

from uuid import UUID

from ceo_voice.context.contracts import EvidenceBundle, EvidenceLane
from ceo_voice.core.exceptions import ContextCompilationError
from ceo_voice.models.enums import ContextRole
from ceo_voice.models.retrieval import RetrievedContext


class EvidenceCompiler:
    """Validate supplied retrieval output without selecting or searching for evidence."""

    def compile(
        self,
        context: RetrievedContext | None,
        *,
        allowed_factual_document_ids: tuple[UUID, ...],
    ) -> EvidenceBundle:
        """Partition supplied items by purpose and enforce factual-source pinning."""

        if context is None:
            return EvidenceBundle(
                retrieval_trace_id=None,
                retrieval_query=None,
                generated_at=None,
                lanes=tuple(EvidenceLane(role=role) for role in ContextRole),
            )
        keys = tuple((item.document_id, item.role) for item in context.items)
        if len(keys) != len(set(keys)):
            raise ContextCompilationError(
                "retrieved evidence contains duplicate document-role pairs",
                details={"reason": "invalid_retrieved_evidence", "trace_id": str(context.trace_id)},
            )
        all_ranks = tuple(item.rank for item in context.items)
        if len(all_ranks) != len(set(all_ranks)):
            raise ContextCompilationError(
                "retrieved evidence ranks must be globally unique",
                details={"reason": "invalid_retrieved_evidence", "trace_id": str(context.trace_id)},
            )
        allowed = set(allowed_factual_document_ids)
        unpinned = tuple(
            item.document_id
            for item in context.items
            if item.role is ContextRole.FACTUAL_EVIDENCE
            and allowed
            and item.document_id not in allowed
        )
        if unpinned:
            raise ContextCompilationError(
                "factual evidence contains documents not pinned by the generation request",
                details={
                    "reason": "unpinned_factual_evidence",
                    "document_ids": tuple(str(item) for item in unpinned),
                },
            )
        lanes = tuple(
            EvidenceLane(
                role=role,
                items=tuple(
                    sorted(
                        (item for item in context.items if item.role is role),
                        key=lambda item: item.rank,
                    )
                ),
            )
            for role in ContextRole
        )
        return EvidenceBundle(
            retrieval_trace_id=context.trace_id,
            retrieval_query=context.query,
            generated_at=context.generated_at,
            lanes=lanes,
        )
