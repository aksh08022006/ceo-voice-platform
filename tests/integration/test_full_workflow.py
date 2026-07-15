"""Real production wiring from curated corpus through the generation boundary."""

import asyncio
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from ceo_voice.context import create_context_compiler
from ceo_voice.evaluation import EvaluationEngine, EvaluationInput, render_evaluation_report
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
    PublishedIntegrationInput,
    PublishedIntegrationRunner,
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
from ceo_voice.revoice import EditedDraft, ReVoiceEngine, ReVoiceInput, ReVoicePolicy
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.services import PublishedProfileBundle, load_published_profile_catalog
from ceo_voice.showcase import ShowcaseWorkflowService
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


class SequenceProvider:
    name = ProviderName.OPENAI

    def __init__(self, outcomes: tuple[str, ...]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            text=self.outcomes.pop(0),
            provider=self.name,
            model=request.model,
            usage=TokenUsage(input_tokens=20, output_tokens=10),
            latency_ms=2,
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


def test_generated_draft_can_flow_through_human_edit_and_revoice(tmp_path: Path) -> None:
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
    real_builder = create_tier1_profile_builder(
        workspace=InMemoryProfileWorkspace(), runtime=runtime
    )
    virality_workspace = InMemoryViralityWorkspace()
    provider = SequenceProvider(
        (
            "Ownership creates speed.\n\nClear decisions compound.",
            "Ownership creates speed.\n\nClear decisions compound momentum.",
        )
    )
    generation_policy = GenerationPolicy(
        provider=ProviderName.OPENAI,
        model="integration-model",
        model_context_tokens=30_000,
    )
    budget = TokenBudgetManager(generation_policy)
    prompt_builder, prompt_renderer = PromptBuilder(budget), PromptRenderer(budget)
    runner = IntegrationRunner(
        profile_builder=cast(
            VoiceProfileBuilder, ApprovedFixtureBuilder(real_builder, authorized_registry)
        ),
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
            policy=generation_policy,
        ),
    )

    outcome = asyncio.run(runner.run(integration_input(tmp_path)))
    artifacts = outcome.artifacts
    assert artifacts.draft is not None
    assert artifacts.context is not None
    assert artifacts.retrieval is not None
    assert artifacts.voice_profile is not None
    assert artifacts.virality_profile is not None
    edited = EditedDraft(
        original=artifacts.draft,
        content="Ownership creates speed.\n\nClear decisions build momentum.",
        edited_at=outcome.completed_at,
    )
    result = asyncio.run(
        ReVoiceEngine(
            provider,
            policy=ReVoicePolicy(
                provider=ProviderName.OPENAI,
                model="integration-model",
            ),
        ).restore(
            ReVoiceInput(
                edited_draft=edited,
                context=artifacts.context,
                retrieval=artifacts.retrieval,
                voice_profile=artifacts.voice_profile,
                virality_profile=artifacts.virality_profile,
                requested_at=outcome.completed_at,
            )
        )
    )

    assert result.content == ("Ownership creates speed.\n\nClear decisions compound momentum.")
    assert result.report.final_validation.valid
    assert result.report.changed_regions == ("editable.line.2",)
    assert provider.calls == 2
    evaluation = asyncio.run(
        EvaluationEngine().evaluate(
            EvaluationInput(
                draft=result,
                context=artifacts.context,
                retrieval=artifacts.retrieval,
                voice_profile=artifacts.voice_profile,
                virality_profile=artifacts.virality_profile,
                edited_draft=edited,
                evaluated_at=outcome.completed_at,
            )
        )
    )
    assert evaluation.retrieval_bundle_id == artifacts.retrieval.bundle_id
    assert evaluation.dimensions
    assert provider.calls == 2, "evaluation remains independent and deterministic by default"
    artifact_root = tmp_path / str(outcome.run_id)
    (artifact_root / "revoiced-draft.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    (artifact_root / "evaluation-report.json").write_text(
        evaluation.model_dump_json(indent=2), encoding="utf-8"
    )
    (artifact_root / "evaluation-report.md").write_text(
        render_evaluation_report(evaluation), encoding="utf-8"
    )


def test_published_release_serving_does_not_rebuild_profiles(tmp_path: Path) -> None:
    runtime = build_tier1_runtime()
    registry = FeatureRegistry.build(
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
    virality_workspace = InMemoryViralityWorkspace()
    provider = NeverCalledProvider()
    policy = GenerationPolicy(
        provider=ProviderName.OPENAI,
        model="integration-model",
        model_context_tokens=30_000,
    )
    budget = TokenBudgetManager(policy)
    prompts, renderer = PromptBuilder(budget), PromptRenderer(budget)
    builder_runner = IntegrationRunner(
        profile_builder=cast(
            VoiceProfileBuilder,
            ApprovedFixtureBuilder(
                create_tier1_profile_builder(workspace=InMemoryProfileWorkspace(), runtime=runtime),
                registry,
            ),
        ),
        virality_builder=create_virality_builder(workspace=virality_workspace),
        virality_workspace=virality_workspace,
        feature_registry=registry,
        context_compiler=create_context_compiler(),
        prompt_builder=prompts,
        prompt_renderer=renderer,
        generation_engine=GenerationEngine(
            provider, prompts, renderer, OutputValidator(), policy=policy
        ),
    )
    command = integration_input(tmp_path)
    built = asyncio.run(builder_runner.run(command))
    assert built.artifacts.voice_profile is not None
    assert built.artifacts.virality_profile is not None
    analysis = asyncio.run(
        virality_workspace.get_analysis(
            built.artifacts.virality_profile.publication.release.analysis_snapshot
        )
    )
    assert analysis is not None
    deployment = PublishedProfileBundle(
        slug="integration-leader",
        name=command.profile_manifest.corpus.identity.display_name,
        role="Integration fixture",
        summary="Pinned deployment bundle used only by the full-system regression.",
        voice_profile=built.artifacts.voice_profile,
        voice_corpus=command.profile_manifest.corpus,
        virality_profile=built.artifacts.virality_profile,
        virality_analysis=analysis,
        virality_corpus=command.virality_corpus,
        feature_registry=registry,
    )
    deployment_root = tmp_path / "deployment"
    deployment_root.mkdir()
    (deployment_root / "integration-leader.json").write_text(
        deployment.model_dump_json(), encoding="utf-8"
    )
    catalog_path = deployment_root / "catalog.json"
    catalog_path.write_text(
        '{"schema_version":"1.0","bundles":["integration-leader.json"]}',
        encoding="utf-8",
    )
    deployed = load_published_profile_catalog(catalog_path)[0]

    served = asyncio.run(
        PublishedIntegrationRunner(
            feature_registry=registry,
            context_compiler=create_context_compiler(),
            prompt_builder=prompts,
            prompt_renderer=renderer,
            generation_engine=GenerationEngine(
                provider, prompts, renderer, OutputValidator(), policy=policy
            ),
        ).run(
            PublishedIntegrationInput(
                run_id=UUID(int=9002),
                profile=deployed.voice_profile,
                profile_corpus=deployed.voice_corpus,
                virality_profile=deployed.virality_profile,
                virality_analysis=deployed.virality_analysis,
                virality_corpus=deployed.virality_corpus,
                request=command.request,
                output_directory=tmp_path,
                started_at=command.started_at,
            )
        )
    )

    assert served.status is IntegrationStatus.SUCCEEDED, served.failure
    assert [item.stage for item in served.timeline] == [
        IntegrationStage.AUTHORIZATION,
        IntegrationStage.CONTEXT,
        IntegrationStage.RETRIEVAL,
        IntegrationStage.PROMPT,
        IntegrationStage.GENERATION,
    ]
    assert served.artifacts.draft is not None
    assert provider.calls == 2

    browser_service = ShowcaseWorkflowService(
        output_directory=tmp_path / "browser",
        provider=provider,
        model="integration-model",
        published_bundles=(deployed,),
    )
    assert browser_service.mode == "published"
    assert [(item.slug, item.status) for item in browser_service.profiles] == [
        ("integration-leader", "published")
    ]
    assert browser_service.walkthroughs == ()
    browser_session = asyncio.run(
        browser_service.generate(
            profile_slug="integration-leader",
            platform=Platform.LINKEDIN,
            content_type="post",
            idea="Explain why clear ownership improves technical execution.",
            constraints=("Avoid unsupported claims.",),
        )
    )
    assert browser_session.outcome.status is IntegrationStatus.SUCCEEDED
    assert [item.stage for item in browser_session.outcome.timeline] == [
        IntegrationStage.AUTHORIZATION,
        IntegrationStage.CONTEXT,
        IntegrationStage.RETRIEVAL,
        IntegrationStage.PROMPT,
        IntegrationStage.GENERATION,
    ]
    assert provider.calls == 3

    unready = built.artifacts.voice_profile.model_copy(
        update={
            "corpus_health": built.artifacts.voice_profile.corpus_health.model_copy(
                update={"generation_ready": False}
            )
        }
    )
    blocked = asyncio.run(
        PublishedIntegrationRunner(
            feature_registry=registry,
            context_compiler=create_context_compiler(),
            prompt_builder=prompts,
            prompt_renderer=renderer,
            generation_engine=GenerationEngine(
                provider, prompts, renderer, OutputValidator(), policy=policy
            ),
        ).run(
            PublishedIntegrationInput(
                run_id=UUID(int=9003),
                profile=unready,
                profile_corpus=command.profile_manifest.corpus,
                virality_profile=built.artifacts.virality_profile,
                virality_analysis=analysis,
                virality_corpus=command.virality_corpus,
                request=command.request,
                output_directory=tmp_path,
                started_at=command.started_at,
            )
        )
    )
    assert blocked.status is IntegrationStatus.BLOCKED
    assert blocked.failure is not None
    assert blocked.failure.details["reason"] == "profile_not_generation_ready"
    assert provider.calls == 3
