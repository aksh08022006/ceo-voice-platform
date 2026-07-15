"""Browser workflow composition over the existing production engines."""

from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from typing import cast
from uuid import UUID, uuid4

from ceo_voice.context import create_context_compiler
from ceo_voice.core.exceptions import IntegrationError
from ceo_voice.evaluation import EvaluationEngine, EvaluationInput, EvaluationReport
from ceo_voice.generation import (
    GenerationEngine,
    GenerationPolicy,
    OutputValidator,
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
)
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.integration import (
    IntegrationInput,
    IntegrationOutcome,
    IntegrationRunner,
    PublishedIntegrationInput,
    PublishedIntegrationRunner,
)
from ceo_voice.models.enums import Platform
from ceo_voice.profiles import (
    InMemoryProfileWorkspace,
    PublishedVoiceProfile,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.prompts import THREAD_SEPARATOR
from ceo_voice.revoice import EditedDraft, ReVoicedDraft, ReVoiceEngine, ReVoiceInput, ReVoicePolicy
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.services.published_profiles import PublishedProfileBundle
from ceo_voice.utils import utc_now
from ceo_voice.virality import InMemoryViralityWorkspace, ViralityProfile, create_virality_builder
from ceo_voice.voice import DownstreamPermission, FeatureRegistry

from .catalog import PROFILES, WALKTHROUGHS, ShowcaseProfile, Walkthrough, profile_by_slug
from .fixtures import NOW, ReviewedShowcaseProfileBuilder, profile_manifest, virality_corpus
from .provider import ShowcaseProvider


@dataclass(slots=True)
class WorkflowSession:
    """Server-owned state needed to continue one governed workflow."""

    id: UUID
    profile: ShowcaseProfile
    outcome: IntegrationOutcome
    edited: EditedDraft | None = None
    revoiced: ReVoicedDraft | None = None
    evaluation: EvaluationReport | None = None


class ShowcaseWorkflowService:
    """Execute end-to-end local workflows without bypassing domain boundaries."""

    def __init__(
        self,
        output_directory: Path | None = None,
        *,
        provider: ModelProvider | None = None,
        model: str = "showcase-deterministic-v1",
        model_context_tokens: int = 30_000,
        maximum_output_tokens: int = 800,
        maximum_provider_retries: int = 2,
        published_bundles: tuple[PublishedProfileBundle, ...] = (),
    ) -> None:
        self._output = output_directory or Path(gettempdir()) / "ceo-voice-showcase"
        self._sessions: dict[UUID, WorkflowSession] = {}
        self._provider = provider
        self._model = model
        self._model_context_tokens = model_context_tokens
        self._maximum_output_tokens = maximum_output_tokens
        self._maximum_provider_retries = maximum_provider_retries
        self._bundles = {bundle.slug: bundle for bundle in published_bundles}
        if self._bundles and provider is None:
            raise IntegrationError("published profile serving requires a configured model provider")

    @property
    def mode(self) -> str:
        """Return the active artifact source exposed by this service."""

        return "published" if self._bundles else "showcase"

    @property
    def profiles(self) -> tuple[ShowcaseProfile, ...]:
        """Project selectable profiles without exposing deployment artifacts over HTTP."""

        if not self._bundles:
            return PROFILES
        return tuple(
            ShowcaseProfile(
                slug=bundle.slug,
                name=bundle.name,
                role=bundle.role,
                summary=bundle.summary,
                status=(
                    "published"
                    if bundle.voice_profile.corpus_health.generation_ready
                    else "not-ready"
                ),
            )
            for bundle in self._bundles.values()
        )

    @property
    def walkthroughs(self) -> tuple[Walkthrough, ...]:
        """Return synthetic walkthroughs only when showcase artifacts are active."""

        return () if self._bundles else WALKTHROUGHS

    async def generate(
        self,
        *,
        profile_slug: str,
        platform: Platform,
        content_type: str,
        idea: str,
        constraints: tuple[str, ...],
    ) -> WorkflowSession:
        """Run corpus-to-draft and retain sealed artifacts for later steps."""

        if self._bundles:
            return await self._generate_published(
                profile_slug=profile_slug,
                platform=platform,
                content_type=content_type,
                idea=idea,
                constraints=constraints,
            )
        profile = profile_by_slug(profile_slug)
        manifest = profile_manifest(profile)
        request_id, run_id = uuid4(), uuid4()
        request = GenerationRequest(
            request_id=request_id,
            tenant_id=manifest.corpus.identity.tenant_id,
            ceo_id=manifest.corpus.identity.leader_id,
            voice_profile_id=manifest.corpus.lineage.id,
            voice_profile_version=1,
            platform=platform,
            topic=idea,
            objective=f"Create a {content_type} that communicates the idea clearly",
            audience="executive and technical readers",
            constraints=constraints,
        )
        provider = self._provider or ShowcaseProvider(
            self._draft(profile_slug, platform, idea, content_type)
        )
        runner = self._runner(provider)
        outcome = await runner.run(
            IntegrationInput(
                run_id=run_id,
                profile_manifest=manifest,
                virality_corpus=virality_corpus(profile),
                request=request,
                output_directory=self._output,
                started_at=NOW,
            )
        )
        if outcome.artifacts.draft is None:
            failure = outcome.failure
            raise IntegrationError(
                "showcase workflow did not produce a draft",
                details={"reason": failure.code if failure else "unknown"},
            )
        session = WorkflowSession(id=run_id, profile=profile, outcome=outcome)
        self._sessions[run_id] = session
        return session

    async def _generate_published(
        self,
        *,
        profile_slug: str,
        platform: Platform,
        content_type: str,
        idea: str,
        constraints: tuple[str, ...],
    ) -> WorkflowSession:
        """Serve one request from exact immutable release artifacts without rebuilding them."""

        try:
            bundle = self._bundles[profile_slug]
        except KeyError as exc:
            raise KeyError(profile_slug) from exc
        provider = self._require(self._provider, "model provider")
        assert isinstance(provider, ModelProvider)
        release = bundle.voice_profile.managed_release.release
        run_id = uuid4()
        started_at = utc_now()
        request = GenerationRequest(
            request_id=uuid4(),
            tenant_id=bundle.voice_corpus.identity.tenant_id,
            ceo_id=bundle.voice_corpus.identity.leader_id,
            voice_profile_id=release.lineage_id,
            voice_profile_version=release.version,
            platform=platform,
            topic=idea,
            objective=f"Create a {content_type} that communicates the idea clearly",
            audience="executive and technical readers",
            constraints=constraints,
        )
        outcome = await self._published_runner(bundle, provider).run(
            PublishedIntegrationInput(
                run_id=run_id,
                profile=bundle.voice_profile,
                profile_corpus=bundle.voice_corpus,
                virality_profile=bundle.virality_profile,
                virality_analysis=bundle.virality_analysis,
                virality_corpus=bundle.virality_corpus,
                request=request,
                output_directory=self._output,
                started_at=started_at,
            )
        )
        if outcome.artifacts.draft is None:
            failure = outcome.failure
            raise IntegrationError(
                "published workflow did not produce a draft",
                details={"reason": failure.code if failure else "unknown"},
            )
        profile = next(item for item in self.profiles if item.slug == profile_slug)
        session = WorkflowSession(id=run_id, profile=profile, outcome=outcome)
        self._sessions[run_id] = session
        return session

    async def revoice(self, session_id: UUID, edited_content: str) -> WorkflowSession:
        """Restore voice against the exact artifacts generated for the session."""

        session = self.get(session_id)
        artifacts = session.outcome.artifacts
        draft = self._require(artifacts.draft, "generated draft")
        edited = EditedDraft(
            original=draft,
            content=edited_content,
            edited_at=session.outcome.completed_at,
        )
        provider = self._provider or ShowcaseProvider(self._restore(edited_content))
        revoiced = await ReVoiceEngine(
            provider,
            policy=ReVoicePolicy(provider=provider.name, model=self._model),
        ).restore(
            ReVoiceInput(
                edited_draft=edited,
                context=self._require(artifacts.context, "generation context"),
                retrieval=self._require(artifacts.retrieval, "retrieval bundle"),
                voice_profile=cast(
                    PublishedVoiceProfile,
                    self._require(artifacts.voice_profile, "voice profile"),
                ),
                virality_profile=cast(
                    ViralityProfile,
                    self._require(artifacts.virality_profile, "virality profile"),
                ),
                requested_at=session.outcome.completed_at,
            )
        )
        session.edited, session.revoiced = edited, revoiced
        session.evaluation = None
        return session

    async def evaluate(self, session_id: UUID) -> WorkflowSession:
        """Evaluate the latest candidate deterministically with evidence traceability."""

        session = self.get(session_id)
        artifacts = session.outcome.artifacts
        candidate = session.revoiced or self._require(artifacts.draft, "generated draft")
        session.evaluation = await EvaluationEngine().evaluate(
            EvaluationInput(
                draft=candidate,
                context=self._require(artifacts.context, "generation context"),
                retrieval=self._require(artifacts.retrieval, "retrieval bundle"),
                voice_profile=cast(
                    PublishedVoiceProfile,
                    self._require(artifacts.voice_profile, "voice profile"),
                ),
                virality_profile=cast(
                    ViralityProfile,
                    self._require(artifacts.virality_profile, "virality profile"),
                ),
                edited_draft=session.edited if session.revoiced else None,
                evaluated_at=session.outcome.completed_at,
            )
        )
        return session

    def get(self, session_id: UUID) -> WorkflowSession:
        """Return an existing session without hidden reconstruction."""

        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(str(session_id)) from exc

    @staticmethod
    def _require(value: object | None, name: str) -> object:
        if value is None:
            raise IntegrationError(f"workflow session is missing {name}")
        return value

    @staticmethod
    def _draft(slug: str, platform: Platform, idea: str, content_type: str) -> str:
        idea = idea.strip().rstrip(".")
        if platform is Platform.X:
            parts = (
                f"A platform shift is underway: {idea}.",
                "The important change is not the demo. It is the infrastructure that lets builders turn capability into reliable systems.",
                "The next chapter belongs to teams that connect ambitious technology to useful work.",
            )
            return THREAD_SEPARATOR.join(parts) if content_type == "thread" else parts[0]
        openings = {
            "ali-ghodsi": "Teams do not need another disconnected demo.",
            "matei-zaharia": "The mechanism matters before the benchmark.",
            "jensen-huang": "Computing is entering a new platform transition.",
        }
        return (
            f"{openings[slug]}\n\n{idea}.\n\n"
            "The practical shift is to connect the technology, the operating model, and clear ownership. "
            "That is how an idea becomes a system people can trust.\n\n"
            "What is the first constraint your team would remove?"
        )

    @staticmethod
    def _restore(content: str) -> str:
        # The zero-credential adapter is intentionally conservative. It still exercises the
        # complete Re-Voice prompt, region, and validation path, but never invents a rewrite.
        # A configured model adapter may propose changes inside the same sealed edit envelope.
        return content

    def _runner(self, provider: ModelProvider) -> IntegrationRunner:
        runtime = build_tier1_runtime()
        registry = FeatureRegistry.build(
            registry_id=runtime.registry.id,
            version=runtime.registry.version,
            definitions=tuple(
                item.model_copy(
                    update={
                        "downstream_permissions": tuple(
                            dict.fromkeys(
                                (*item.downstream_permissions, DownstreamPermission.GENERATE)
                            )
                        )
                    }
                )
                for item in runtime.registry.definitions
            ),
            created_at=runtime.registry.created_at,
        )
        workspace = InMemoryProfileWorkspace()
        builder = ReviewedShowcaseProfileBuilder(
            create_tier1_profile_builder(workspace=workspace, runtime=runtime), registry
        )
        virality_workspace = InMemoryViralityWorkspace()
        policy = GenerationPolicy(
            provider=provider.name,
            model=self._model,
            model_context_tokens=self._model_context_tokens,
            maximum_output_tokens=self._maximum_output_tokens,
            maximum_provider_retries=self._maximum_provider_retries,
        )
        budget = TokenBudgetManager(policy)
        prompts, renderer = PromptBuilder(budget), PromptRenderer(budget)
        return IntegrationRunner(
            profile_builder=cast(VoiceProfileBuilder, builder),
            virality_builder=create_virality_builder(workspace=virality_workspace),
            virality_workspace=virality_workspace,
            feature_registry=registry,
            context_compiler=create_context_compiler(),
            prompt_builder=prompts,
            prompt_renderer=renderer,
            generation_engine=GenerationEngine(
                provider,
                prompts,
                renderer,
                OutputValidator(),
                policy=policy,
            ),
        )

    def _published_runner(
        self, bundle: PublishedProfileBundle, provider: ModelProvider
    ) -> PublishedIntegrationRunner:
        policy = GenerationPolicy(
            provider=provider.name,
            model=self._model,
            model_context_tokens=self._model_context_tokens,
            maximum_output_tokens=self._maximum_output_tokens,
            maximum_provider_retries=self._maximum_provider_retries,
        )
        budget = TokenBudgetManager(policy)
        prompts, renderer = PromptBuilder(budget), PromptRenderer(budget)
        return PublishedIntegrationRunner(
            feature_registry=bundle.feature_registry,
            context_compiler=create_context_compiler(),
            prompt_builder=prompts,
            prompt_renderer=renderer,
            generation_engine=GenerationEngine(
                provider,
                prompts,
                renderer,
                OutputValidator(),
                policy=policy,
            ),
        )
