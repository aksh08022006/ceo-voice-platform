"""Deterministic compilation of HVM, VKR, intent, constraints, and supplied evidence."""

from ceo_voice.context.compiler import ContextCompiler
from ceo_voice.context.composition import create_context_compiler
from ceo_voice.context.constraints import ConstraintCompiler
from ceo_voice.context.contracts import (
    CompilationInput,
    CompilationReport,
    CompiledConstraint,
    CompiledVoiceFeature,
    CompiledVoiceInteraction,
    ConfidenceSummary,
    ConfidenceThresholds,
    ConstraintBundle,
    ConstraintSummary,
    ContextCompilationPolicy,
    ContextCompilerVersion,
    EvidenceBundle,
    EvidenceLane,
    GenerationContext,
    GenerationIntent,
    IgnoredKnowledge,
    PlatformContract,
    StructuralGuidance,
    StructuralSelectionPolicy,
    TraceReference,
    UserConstraint,
    ViralityTarget,
    VoiceConfidence,
    VoiceTarget,
    compute_generation_context_hash,
    generation_context_id,
)
from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
    IgnoredReason,
    TraceArtifactKind,
    VoiceResolutionSource,
)
from ceo_voice.context.evidence import EvidenceCompiler
from ceo_voice.context.platforms import PlatformContractCatalog
from ceo_voice.context.structure import ViralityCompiler
from ceo_voice.context.voice import VoiceCompiler
from ceo_voice.core.exceptions import ContextCompilationError

__all__ = [
    "CompilationInput",
    "CompilationReport",
    "CompiledConstraint",
    "CompiledVoiceFeature",
    "CompiledVoiceInteraction",
    "ConfidenceSummary",
    "ConfidenceThresholds",
    "ConstraintBundle",
    "ConstraintCategory",
    "ConstraintCompiler",
    "ConstraintOperator",
    "ConstraintStrength",
    "ConstraintSummary",
    "ContextCompilationError",
    "ContextCompilationPolicy",
    "ContextCompiler",
    "ContextCompilerVersion",
    "EvidenceBundle",
    "EvidenceCompiler",
    "EvidenceLane",
    "GenerationContext",
    "GenerationIntent",
    "IgnoredKnowledge",
    "IgnoredReason",
    "PlatformContract",
    "PlatformContractCatalog",
    "StructuralGuidance",
    "StructuralSelectionPolicy",
    "TraceArtifactKind",
    "TraceReference",
    "UserConstraint",
    "ViralityCompiler",
    "ViralityTarget",
    "VoiceCompiler",
    "VoiceConfidence",
    "VoiceResolutionSource",
    "VoiceTarget",
    "compute_generation_context_hash",
    "create_context_compiler",
    "generation_context_id",
]
