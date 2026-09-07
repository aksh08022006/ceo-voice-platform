"""Browser workflow composition over the existing production engines."""

from dataclasses import dataclass
from itertools import count
from pathlib import Path
from tempfile import gettempdir
from typing import Literal, cast
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
from ceo_voice.generation.editor_revision import RevisionProposal, revise_flagged_spans
from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import BriefSource, FidelityPolicy, FidelityReview
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.integration import (
    IntegrationInput,
    IntegrationOutcome,
    IntegrationRunner,
    PublishedIntegrationInput,
    PublishedIntegrationRunner,
)
from ceo_voice.integration.artifacts import ArtifactWriter
from ceo_voice.integration.ports import RetrievalRankingPreparer
from ceo_voice.models.communication import CommentContext, ReplyIntent
from ceo_voice.models.enums import ContentType, Platform
from ceo_voice.models.expression import ExpressionDirection
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
from ceo_voice.services.expression import build_expression_profile
from ceo_voice.services.published_profiles import PublishedProfileBundle
from ceo_voice.utils import utc_now
from ceo_voice.virality import InMemoryViralityWorkspace, ViralityProfile, create_virality_builder
from ceo_voice.voice import DownstreamPermission, FeatureRegistry

from .catalog import PROFILES, WALKTHROUGHS, ShowcaseProfile, Walkthrough, profile_by_slug
from .fixtures import NOW, ReviewedShowcaseProfileBuilder, profile_manifest, virality_corpus
from .provider import ShowcaseProvider

SESSION_CACHE_LIMIT = 32


@dataclass(slots=True)
class WorkflowSession:
    """Server-owned state needed to continue one governed workflow."""

    id: UUID
    profile: ShowcaseProfile
    outcome: IntegrationOutcome
    edited: EditedDraft | None = None
    revoiced: ReVoicedDraft | None = None
    evaluation: EvaluationReport | None = None
    revision_count: int = 0


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
        retrieval_ranking: RetrievalRankingPreparer | None = None,
        artifact_storage: Literal["filesystem", "memory"] = "filesystem",
        fidelity_reviewer: FidelityReviewer | None = None,
    ) -> None:
        self._artifacts = ArtifactWriter(storage=artifact_storage)
        self._output = output_directory or (
            Path(gettempdir()) / "ceo-voice-showcase"
            if artifact_storage == "filesystem"
            else Path("memory-artifacts")
        )
        self._sessions: dict[UUID, WorkflowSession] = {}
        self._variation_sequence = count()
        self._provider = provider
        self._retrieval_ranking = retrieval_ranking
        self._model = model
        self._model_context_tokens = model_context_tokens
        self._maximum_output_tokens = maximum_output_tokens
        self._maximum_provider_retries = maximum_provider_retries
        self._fidelity_reviewer = fidelity_reviewer
        self._bundles = {bundle.slug: bundle for bundle in published_bundles}
        if self._bundles and provider is None:
            raise IntegrationError("published profile serving requires a configured model provider")

    @property
    def mode(self) -> str:
        """Return the active artifact source exposed by this service."""

        if not self._bundles:
            return "showcase"
        return (
            "development"
            if any(bundle.artifact_status == "development" for bundle in self._bundles.values())
            else "published"
        )

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
                    bundle.artifact_status
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

    def published_bundle(self, profile_slug: str) -> PublishedProfileBundle:
        """Return one governed deployment bundle for read-only inspection.

        The browser API uses this boundary to project aggregate HVM analytics without exposing
        raw corpus content or reaching into the service's private deployment state.
        """

        try:
            return self._bundles[profile_slug]
        except KeyError as exc:
            raise KeyError(profile_slug) from exc

    @property
    def published_bundles(self) -> tuple[PublishedProfileBundle, ...]:
        """Return immutable deployment bundles for aggregate cross-profile comparison."""

        return tuple(self._bundles.values())

    async def generate(
        self,
        *,
        profile_slug: str,
        platform: Platform,
        content_type: str,
        idea: str,
        constraints: tuple[str, ...],
        thread_post_count: int | None = None,
        virality_influence: float = 0.125,
        minimum_words: int | None = None,
        maximum_words: int | None = None,
        comment_context: CommentContext | None = None,
        expression: ExpressionDirection | None = None,
        reserved_session_id: UUID | None = None,
    ) -> WorkflowSession:
        """Run corpus-to-draft and retain sealed artifacts for later steps."""

        if self._bundles:
            return await self._generate_published(
                profile_slug=profile_slug,
                platform=platform,
                content_type=content_type,
                idea=idea,
                constraints=constraints,
                thread_post_count=thread_post_count,
                virality_influence=virality_influence,
                minimum_words=minimum_words,
                maximum_words=maximum_words,
                comment_context=comment_context,
                expression=expression,
                reserved_session_id=reserved_session_id,
            )
        profile = profile_by_slug(profile_slug)
        manifest = profile_manifest(profile)
        request_id, run_id = uuid4(), reserved_session_id or uuid4()
        request = GenerationRequest(
            request_id=request_id,
            tenant_id=manifest.corpus.identity.tenant_id,
            ceo_id=manifest.corpus.identity.leader_id,
            voice_profile_id=manifest.corpus.lineage.id,
            voice_profile_version=1,
            platform=platform,
            content_type=ContentType(content_type),
            thread_post_count=thread_post_count,
            virality_influence=virality_influence,
            minimum_words=minimum_words,
            maximum_words=maximum_words,
            topic=idea,
            expression=expression,
            comment_context=comment_context,
            objective=(
                "Write a concise comment preserving the editor's selected reply intent and supplied points"
                if comment_context
                else f"Create a {content_type} that communicates the idea clearly"
            ),
            audience="executive and technical readers",
            constraints=constraints,
        )
        provider = self._provider or ShowcaseProvider(
            self._draft(
                profile_slug,
                platform,
                idea,
                content_type,
                minimum_words,
                variation_index=next(self._variation_sequence),
                thread_post_count=thread_post_count,
                comment_context=comment_context,
            )
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
        return self._remember(session)

    async def _generate_published(
        self,
        *,
        profile_slug: str,
        platform: Platform,
        content_type: str,
        idea: str,
        constraints: tuple[str, ...],
        thread_post_count: int | None,
        virality_influence: float,
        minimum_words: int | None,
        maximum_words: int | None,
        comment_context: CommentContext | None,
        expression: ExpressionDirection | None = None,
        reserved_session_id: UUID | None = None,
    ) -> WorkflowSession:
        """Serve one request from exact immutable release artifacts without rebuilding them."""

        try:
            bundle = self._bundles[profile_slug]
        except KeyError as exc:
            raise KeyError(profile_slug) from exc
        provider = self._require(self._provider, "model provider")
        assert isinstance(provider, ModelProvider)
        release = bundle.voice_profile.managed_release.release
        run_id = reserved_session_id or uuid4()
        started_at = utc_now()
        request = GenerationRequest(
            request_id=uuid4(),
            tenant_id=bundle.voice_corpus.identity.tenant_id,
            ceo_id=bundle.voice_corpus.identity.leader_id,
            voice_profile_id=release.lineage_id,
            voice_profile_version=release.version,
            platform=platform,
            content_type=ContentType(content_type),
            thread_post_count=thread_post_count,
            virality_influence=virality_influence,
            minimum_words=minimum_words,
            maximum_words=maximum_words,
            topic=idea,
            expression=expression,
            expression_profile=build_expression_profile(bundle.voice_corpus, platform),
            comment_context=comment_context,
            objective=(
                "Write a concise comment preserving the editor's selected reply intent and supplied points"
                if comment_context
                else f"Create a {content_type} that communicates the idea clearly"
            ),
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
        return self._remember(session)

    async def revoice(
        self, session_id: UUID, edited_content: str, editor_note: str | None = None
    ) -> WorkflowSession:
        """Restore voice against the exact artifacts generated for the session."""

        session = self.get(session_id)
        artifacts = session.outcome.artifacts
        draft = self._require(artifacts.draft, "generated draft")
        previous_revision = session.revoiced
        revision_count = session.revision_count
        requested_at = utc_now()
        edited = EditedDraft(
            original=draft,
            previous_revision=previous_revision,
            content=edited_content,
            edited_at=requested_at,
            editor_note=editor_note,
        )
        provider = self._provider or ShowcaseProvider(self._restore(edited_content))
        revoiced = await ReVoiceEngine(
            provider,
            policy=ReVoicePolicy(
                provider=provider.name,
                model=self._model,
                model_context_tokens=self._model_context_tokens,
                maximum_output_tokens=self._maximum_output_tokens,
                maximum_provider_retries=self._maximum_provider_retries,
            ),
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
                requested_at=requested_at,
            )
        )
        if session.revision_count != revision_count:
            raise IntegrationError("A newer revision is available. Reload before re-voicing.")
        session.edited, session.revoiced = edited, revoiced
        session.revision_count += 1
        session.evaluation = None
        return session

    async def revise_editor(
        self,
        *,
        request_id: UUID,
        content: str,
        review: FidelityReview,
        sources: tuple[BriefSource, ...],
    ) -> RevisionProposal:
        """One shared-provider call, without retries, for exact-span editorial correction."""
        if self._provider is None:
            raise IntegrationError("editor revision requires a configured model provider")
        return await revise_flagged_spans(
            self._provider,
            model=self._model,
            maximum_output_tokens=self._maximum_output_tokens,
            request_id=request_id,
            content=content,
            review=review,
            sources=sources,
        )

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

    def resume(self, session: WorkflowSession) -> WorkflowSession:
        """Install a server-authenticated continuation snapshot for one request."""

        if session.profile.slug not in self._bundles:
            raise KeyError(session.profile.slug)
        return self._remember(session)

    def _remember(self, session: WorkflowSession) -> WorkflowSession:
        """Bound generated and resumed sessions; portable continuation retains evicted state."""

        self._sessions.pop(session.id, None)
        self._sessions[session.id] = session
        while len(self._sessions) > SESSION_CACHE_LIMIT:
            self._sessions.pop(next(iter(self._sessions)))
        return session

    @staticmethod
    def _require(value: object | None, name: str) -> object:
        if value is None:
            raise IntegrationError(f"workflow session is missing {name}")
        return value

    @staticmethod
    def _draft(
        slug: str,
        platform: Platform,
        idea: str,
        content_type: str,
        minimum_words: int | None,
        *,
        variation_index: int,
        thread_post_count: int | None = None,
        comment_context: CommentContext | None = None,
    ) -> str:
        idea = idea.strip().rstrip(".")
        if comment_context:
            lead = {
                ReplyIntent.ADD_PERSPECTIVE: "An additional perspective:",
                ReplyIntent.ASK_QUESTION: "A question worth exploring:",
                ReplyIntent.RESPECTFULLY_DISAGREE: "I see the point differently:",
                ReplyIntent.ACKNOWLEDGE: "This is a useful point to recognize:",
                ReplyIntent.ANSWER: "One way to answer that:",
            }[comment_context.reply_intent]
            content = f"{lead} {idea[:180]}{('?') if comment_context.reply_intent is ReplyIntent.ASK_QUESTION else '.'}"
            if platform is Platform.LINKEDIN and len(content.split()) < 40:
                content += (
                    " The practical details deserve attention: what changes for the people using "
                    "the system, which assumptions need testing, and how we can tell whether the "
                    "approach works in the context being discussed."
                )
            return content
        if platform is Platform.X:
            idea = idea[:180].rstrip()
            opening_options = (
                f"A platform shift is underway: {idea}.",
                f"The practical consequence of {idea} is bigger than the demo.",
                f"{idea} changes what builders can put into production.",
            )
            parts = (
                opening_options[variation_index % len(opening_options)],
                "The important change is not the demo. It is the infrastructure that lets builders turn capability into reliable systems.",
                "The next chapter belongs to teams that connect ambitious technology to useful work.",
                "Clear interfaces let teams test each component, understand failure modes, and improve the system without replacing every part.",
                "The useful question is where this approach removes a real constraint for builders and the people using what they build.",
            )
            return (
                THREAD_SEPARATOR.join(parts[:thread_post_count])
                if content_type == "thread"
                else parts[0]
            )
        openings = {
            "ali-ghodsi": "Teams do not need another disconnected demo.",
            "matei-zaharia": "The mechanism matters before the benchmark.",
            "jensen-huang": "Computing is entering a new platform transition.",
        }
        lead_options = (
            openings[slug],
            f"{idea} is a practical infrastructure shift.",
            "The architecture matters more than the announcement.",
        )
        lead = lead_options[variation_index % len(lead_options)]
        closing_options = (
            "The opportunity is to remove the first constraint that keeps the idea from production.",
            "Progress compounds when the operating model is as clear as the technology.",
            "The next step is turning this capability into something teams can trust every day.",
        )
        closing = closing_options[variation_index % len(closing_options)]
        compact = (
            f"{lead}\n\n{idea}.\n\n"
            "The practical shift is to connect the technology, the operating model, and clear ownership. "
            f"That is how an idea becomes a system people can trust.\n\n{closing}"
        )
        if minimum_words is None or len(compact.split()) >= minimum_words:
            return compact
        return (
            f"{openings[slug]}\n\n{idea}.\n\n"
            "Open systems create a durable advantage because customers and builders can inspect "
            "the interfaces, extend the technology, and choose how their data moves. That freedom "
            "does not weaken execution. It creates a larger community that can test ideas, expose "
            "limitations, and improve the foundation together.\n\n"
            "The practical opportunity is to connect the technology, the operating model, and "
            "clear ownership. Teams should be able to adopt the strongest parts without rebuilding "
            "everything around them or accepting a new point of lock-in. When the architecture is "
            "open, progress compounds across companies rather than staying inside one roadmap.\n\n"
            "This is ultimately about giving customers a simpler path from an ambitious idea to a "
            "system they can trust in production. We are excited to keep working with the community, "
            "make the interfaces clearer, and help more teams build on an open foundation.\n\n"
            "The next chapter will be built in the open."
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
            fidelity=(
                self._fidelity_reviewer.policy if self._fidelity_reviewer else FidelityPolicy()
            ),
        )
        budget = TokenBudgetManager(policy)
        prompts, renderer = PromptBuilder(budget), PromptRenderer(budget)
        return IntegrationRunner(
            artifacts=self._artifacts,
            profile_builder=cast(VoiceProfileBuilder, builder),
            virality_builder=create_virality_builder(workspace=virality_workspace),
            virality_workspace=virality_workspace,
            feature_registry=registry,
            retrieval_ranking=self._retrieval_ranking,
            context_compiler=create_context_compiler(),
            prompt_builder=prompts,
            prompt_renderer=renderer,
            generation_engine=GenerationEngine(
                provider,
                prompts,
                renderer,
                OutputValidator(),
                policy=policy,
                fidelity_reviewer=self._fidelity_reviewer,
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
            fidelity=(
                self._fidelity_reviewer.policy if self._fidelity_reviewer else FidelityPolicy()
            ),
        )
        budget = TokenBudgetManager(policy)
        prompts, renderer = PromptBuilder(budget), PromptRenderer(budget)
        return PublishedIntegrationRunner(
            artifacts=self._artifacts,
            feature_registry=bundle.feature_registry,
            retrieval_ranking=self._retrieval_ranking,
            context_compiler=create_context_compiler(),
            prompt_builder=prompts,
            prompt_renderer=renderer,
            generation_engine=GenerationEngine(
                provider,
                prompts,
                renderer,
                OutputValidator(),
                policy=policy,
                fidelity_reviewer=self._fidelity_reviewer,
            ),
        )
