"""Production composition root for context-compilation policy dependencies."""

from datetime import date

from ceo_voice.context.compiler import ContextCompiler
from ceo_voice.context.constraints import ConstraintCompiler
from ceo_voice.context.contracts import (
    CompiledConstraint,
    ContextCompilationPolicy,
    ContextCompilerVersion,
    PlatformContract,
)
from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
)
from ceo_voice.context.platforms import PlatformContractCatalog
from ceo_voice.models.enums import Platform


def create_context_compiler(*, policy: ContextCompilationPolicy | None = None) -> ContextCompiler:
    """Create a compiler with explicit, versioned platform and safety policy."""

    platform_version = ContextCompilerVersion(major=2026, minor=7, patch=0)
    catalog = PlatformContractCatalog(
        (
            PlatformContract(
                platform=Platform.LINKEDIN,
                version=platform_version,
                maximum_characters=3_000,
                thread_output_supported=False,
                maximum_thread_posts=None,
                source_name="LinkedIn UGC Post API",
                source_reference=(
                    "https://learn.microsoft.com/en-us/linkedin/compliance/"
                    "integrations/shares/ugc-post-api"
                ),
                verified_on=date(2026, 7, 14),
            ),
            PlatformContract(
                platform=Platform.X,
                version=platform_version,
                maximum_characters=280,
                thread_output_supported=True,
                maximum_thread_posts=5,
                source_name="X character-counting documentation",
                source_reference="https://docs.x.com/fundamentals/counting-characters",
                verified_on=date(2026, 7, 14),
            ),
        )
    )
    safety = (
        CompiledConstraint(
            constraint_id="safety.factual_claims_grounded",
            category=ConstraintCategory.SAFETY,
            strength=ConstraintStrength.HARD,
            operator=ConstraintOperator.EQUALS,
            key="safety.factual_claims_grounded",
            value=True,
            priority=100,
            source="context_compiler_policy:1.0.0",
            rationale="new factual claims must be supported by supplied factual evidence",
        ),
        CompiledConstraint(
            constraint_id="safety.fabricated_quotes_prohibited",
            category=ConstraintCategory.SAFETY,
            strength=ConstraintStrength.HARD,
            operator=ConstraintOperator.PROHIBIT,
            key="content.fabricated_quote",
            value=True,
            priority=100,
            source="context_compiler_policy:1.0.0",
            rationale="the output must not invent quotations attributed to people",
        ),
    )
    return ContextCompiler(
        platform_catalog=catalog,
        policy=policy,
        constraint_compiler=ConstraintCompiler(safety_constraints=safety),
    )
