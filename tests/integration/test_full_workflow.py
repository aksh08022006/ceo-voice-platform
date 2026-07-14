"""Real production wiring from curated corpus through the generation boundary."""

import asyncio
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from ceo_voice.context import create_context_compiler
from ceo_voice.generation import (
    GenerationEngine,
    GenerationPolicy,
    OutputValidator,
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
)
from ceo_voice.generation.contracts import ProviderRequest, ProviderResult, TokenUsage
from ceo_voice.generation.enums import ProviderName
from ceo_voice.integration import (
    IntegrationInput,
    IntegrationRunner,
    create_local_integration_runner,
)
from ceo_voice.integration.config import load_integration_input
from ceo_voice.integration.contracts import IntegrationStage, IntegrationStatus
from ceo_voice.models.enums import Platform
from ceo_voice.profiles import (
    InMemoryProfileWorkspace,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.virality import InMemoryViralityWorkspace, create_virality_builder
from ceo_voice.voice import DecisionState, DownstreamPermission, FeatureRegistry
from tests.unit.profiles.factories import manifest
from tests.unit.virality.factories import corpus


class NeverCalledProvider:
    name = ProviderName.OPENAI

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            text="This must not run for a descriptive-only profile.",
            provider=self.name,
            model=request.model,
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            latency_ms=1,
        )


class ApprovedFixtureBuilder:
    """Test-only review gate that explicitly promotes a real Tier-1 build."""

    def __init__(self, builder: VoiceProfileBuilder, registry: FeatureRegistry) -> None:
        self._builder = builder
        self._registry = registry

    async def build(self, command: Any) -> Any:
        profile = await self._builder.build(command)
        release = profile.managed_release.release

        def confidence(value: Any) -> Any:
            return value.model_copy(
                update={
                    "measurement_reliability": 1,
                    "attribution_reliability": 1,
                    "coverage": 1,
                    "effective_support": min(1, value.evidence_count),
                    "context_diversity": 1,
                    "stability": 1,
                    "cross_context_robustness": 1,
                    "nuisance_robustness": 1,
                    "distinctiveness": 1,
                    "freshness": 1,
                    "calibration": 1,
                    "independent_cluster_count": min(1, value.evidence_count),
                }
            )

        components = release.components.model_copy(
            update={
                "aggregates": tuple(
                    item.model_copy(
                        update={
                            "confidence": confidence(item.confidence),
                            "decision_state": DecisionState.ACTIONABLE_STRONG,
                        }
                    )
                    for item in release.components.aggregates
                ),
                "residuals": tuple(
                    item.model_copy(
                        update={
                            "confidence": confidence(item.confidence),
                            "decision_state": DecisionState.ACTIONABLE_STRONG,
                        }
                    )
                    for item in release.components.residuals
                ),
                "conditional_residuals": tuple(
                    item.model_copy(
                        update={
                            "confidence": confidence(item.confidence),
                            "decision_state": DecisionState.ACTIONABLE_STRONG,
                        }
                    )
                    for item in release.components.conditional_residuals
                ),
            }
        )
        authorized_release = release.model_copy(
            update={"registry": self._registry.reference, "components": components}
        )
        report = profile.validation_report.model_copy(
            update={"release_content_hash": authorized_release.content_hash}
        )
        managed = profile.managed_release.model_copy(
            update={"release": authorized_release, "validation_report": report}
        )
        return profile.model_copy(
            update={
                "managed_release": managed,
                "validation_report": report,
                "corpus_health": profile.corpus_health.model_copy(
                    update={"generation_ready": True}
                ),
                "inspection": profile.inspection.model_copy(
                    update={"release_content_hash": authorized_release.content_hash}
                ),
                "retrieval_projection": profile.retrieval_projection.model_copy(
                    update={
                        "release_content_hash": authorized_release.content_hash,
                    }
                ),
            }
        )


def integration_input(output: Path) -> IntegrationInput:
    profile_manifest = manifest(1, 2)
    tenant_id = profile_manifest.corpus.identity.tenant_id
    source = corpus(1, 2, 3, 4)
    virality = source.model_copy(
        update={
            "tenant_id": tenant_id,
            "items": tuple(
                item.model_copy(
                    update={"document": item.document.model_copy(update={"tenant_id": tenant_id})}
                )
                for item in source.items
            ),
        }
    )
    request = GenerationRequest(
        request_id=UUID(int=8001),
        tenant_id=tenant_id,
        ceo_id=profile_manifest.corpus.identity.leader_id,
        voice_profile_id=profile_manifest.corpus.lineage.id,
        voice_profile_version=1,
        platform=Platform.LINKEDIN,
        topic="Why clear ownership improves execution",
        objective="Teach operating leaders",
        audience="technology executives",
    )
    return IntegrationInput(
        run_id=UUID(int=8002),
        profile_manifest=profile_manifest,
        virality_corpus=virality,
        request=request,
        output_directory=output,
        started_at=profile_manifest.requested_at,
    )


def test_real_tier1_workflow_exposes_generation_authority_gap_with_artifacts(
    tmp_path: Path,
) -> None:
    provider = NeverCalledProvider()
    runner = create_local_integration_runner(
        provider,
        generation_policy=GenerationPolicy(
            provider=ProviderName.OPENAI,
            model="integration-model",
            model_context_tokens=10_000,
        ),
    )

    outcome = asyncio.run(runner.run(integration_input(tmp_path)))

    assert outcome.status is IntegrationStatus.BLOCKED
    assert outcome.failure is not None
    assert outcome.failure.details["reason"] == "profile_not_generation_ready"
    assert outcome.failure.stage is IntegrationStage.AUTHORIZATION
    assert outcome.artifacts.voice_profile is not None
    assert outcome.artifacts.virality_profile is not None
    assert outcome.artifacts.context is None
    assert provider.calls == 0
    assert [item.stage for item in outcome.timeline] == [
        IntegrationStage.PROFILE,
        IntegrationStage.VIRALITY,
        IntegrationStage.AUTHORIZATION,
    ]
    artifact_root = tmp_path / str(outcome.run_id)
    assert (artifact_root / "voice-profile.json").exists()
    assert (artifact_root / "virality-profile.json").exists()
    assert (artifact_root / "integration-outcome.json").exists()


def test_integration_command_round_trips_through_validated_configuration(tmp_path: Path) -> None:
    command = integration_input(tmp_path)
    path = tmp_path / "integration.json"
    path.write_text(command.model_dump_json(), encoding="utf-8")
    assert load_integration_input(path) == command


def test_complete_workflow_reaches_validated_draft_with_explicitly_approved_fixture(
    tmp_path: Path,
) -> None:
    runtime = build_tier1_runtime()
    authorized_registry = FeatureRegistry.build(
        registry_id=runtime.registry.id,
        version=runtime.registry.version,
        definitions=tuple(
            item.model_copy(
                update={
                    "downstream_permissions": (
                        *item.downstream_permissions,
                        DownstreamPermission.GENERATE,
                    )
                }
            )
            for item in runtime.registry.definitions
        ),
        created_at=runtime.registry.created_at,
    )
    profile_workspace = InMemoryProfileWorkspace()
    real_builder = create_tier1_profile_builder(
        workspace=profile_workspace,
        runtime=runtime,
    )
    approved = ApprovedFixtureBuilder(real_builder, authorized_registry)
    virality_workspace = InMemoryViralityWorkspace()
    provider = NeverCalledProvider()
    policy = GenerationPolicy(
        provider=ProviderName.OPENAI,
        model="integration-model",
        model_context_tokens=30_000,
    )
    budget = TokenBudgetManager(policy)
    prompt_builder = PromptBuilder(budget)
    prompt_renderer = PromptRenderer(budget)
    runner = IntegrationRunner(
        profile_builder=cast(VoiceProfileBuilder, approved),
        virality_builder=create_virality_builder(workspace=virality_workspace),
        virality_workspace=virality_workspace,
        feature_registry=authorized_registry,
        context_compiler=create_context_compiler(),
        prompt_builder=prompt_builder,
        prompt_renderer=prompt_renderer,
        generation_engine=GenerationEngine(
            provider,
            prompt_builder,
            prompt_renderer,
            OutputValidator(),
            policy=policy,
        ),
    )

    outcome = asyncio.run(runner.run(integration_input(tmp_path)))

    assert outcome.status is IntegrationStatus.SUCCEEDED, outcome.failure
    assert outcome.failure is None
    assert outcome.artifacts.context is not None
    assert outcome.artifacts.retrieval is not None
    assert outcome.artifacts.rendered_prompt is not None
    assert outcome.artifacts.draft is not None
    assert outcome.artifacts.draft.report.final_validation.valid
    assert provider.calls == 1
    assert outcome.metrics.evidence_items > 0
    assert outcome.metrics.prompt_input_tokens > 0
    assert outcome.metrics.provider_attempts == 1
    artifact_root = tmp_path / str(outcome.run_id)
    for name in (
        "generation-context.json",
        "retrieval-bundle.json",
        "rendered-prompt.json",
        "generated-draft.json",
        "output-validation.json",
        "generation-report.json",
    ):
        assert (artifact_root / name).exists()
