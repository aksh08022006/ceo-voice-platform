"""Product-facing generation orchestration."""

from uuid import NAMESPACE_URL, uuid5

from ceo_voice.core.exceptions import GenerationValidationError, ProviderError
from ceo_voice.generation.contracts import (
    ConstraintResult,
    GeneratedDraft,
    GenerationAttempt,
    GenerationInput,
    GenerationPolicy,
    GenerationReport,
    ProviderRequest,
    TokenUsage,
)
from ceo_voice.generation.enums import AttemptKind
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.generation.postprocessing import PostProcessor
from ceo_voice.generation.prompting import PromptBuilder, PromptRenderer
from ceo_voice.generation.retry import RetryStrategy
from ceo_voice.generation.validation import (
    OutputValidator,
    ThreadGenerator,
    validate_generation_input,
)


class GenerationEngine:
    """Run the only model-calling workflow in the platform."""

    def __init__(
        self,
        provider: ModelProvider,
        builder: PromptBuilder,
        renderer: PromptRenderer,
        validator: OutputValidator,
        *,
        policy: GenerationPolicy,
        threads: ThreadGenerator | None = None,
        retry: RetryStrategy | None = None,
        post_processor: PostProcessor | None = None,
    ) -> None:
        if provider.name is not policy.provider:
            raise ValueError("provider and generation policy must agree")
        self._provider, self._builder, self._renderer, self._validator, self._policy = (
            provider,
            builder,
            renderer,
            validator,
            policy,
        )
        self._threads = threads or ThreadGenerator()
        self._retry = retry or RetryStrategy(policy)
        self._post_processor = post_processor or PostProcessor()

    async def generate(self, value: GenerationInput) -> GeneratedDraft:
        validate_generation_input(value)
        attempts: list[GenerationAttempt] = []
        feedback: tuple[str, ...] = ()
        provider_failures = 0
        validation_failures = 0
        while True:
            rendered = self._renderer.render(self._builder.build(value, repair_feedback=feedback))
            kind = (
                AttemptKind.INITIAL
                if not attempts
                else (AttemptKind.VALIDATION_REPAIR if feedback else AttemptKind.PROVIDER_RETRY)
            )
            try:
                result = await self._provider.generate(
                    ProviderRequest(
                        request_id=value.request.request_id,
                        system=rendered.system,
                        user=rendered.user,
                        model=self._policy.model,
                        maximum_output_tokens=self._policy.maximum_output_tokens,
                    )
                )
            except ProviderError as error:
                attempts.append(
                    GenerationAttempt(
                        number=len(attempts) + 1,
                        kind=kind,
                        prompt_version=rendered.version,
                        provider=self._policy.provider,
                        model=self._policy.model,
                        latency_ms=0,
                        usage=None,
                        validation=None,
                        error_code=error.code,
                    )
                )
                if not self._retry.provider_allowed(error, provider_failures):
                    raise
                provider_failures += 1
                feedback = ()
                continue
            validation = self._validator.validate(result.text, value, self._policy)
            attempts.append(
                GenerationAttempt(
                    number=len(attempts) + 1,
                    kind=kind,
                    prompt_version=rendered.version,
                    provider=result.provider,
                    model=result.model,
                    latency_ms=result.latency_ms,
                    usage=result.usage,
                    validation=validation,
                )
            )
            if validation.valid:
                content = self._post_processor.process(result.text)
                break
            if not self._retry.repair_allowed(validation_failures):
                raise GenerationValidationError(
                    "provider could not produce a valid draft",
                    details={"findings": [item.code.value for item in validation.findings]},
                )
            validation_failures += 1
            feedback = tuple(item.message for item in validation.findings if item.blocking)
        usages = tuple(item.usage for item in attempts if item.usage is not None)
        constraint_results = tuple(
            ConstraintResult(
                constraint_id=item.constraint_id,
                satisfied=True,
                detail="validated through compiled generation constraints",
            )
            for item in value.context.constraints.constraints
        )
        report = GenerationReport(
            engine_version=self._policy.version,
            prompt_version=rendered.version,
            retrieval_bundle_id=value.retrieval.bundle_id,
            selected_evidence_ids=rendered.included_evidence_ids,
            voice_feature_ids=tuple(item.feature_id for item in value.retrieval.voice_features),
            structural_pattern_ids=tuple(
                item.pattern_id for item in value.retrieval.structural_guidance
            ),
            provider=result.provider,
            model=result.model,
            attempts=tuple(attempts),
            total_latency_ms=sum(item.latency_ms for item in attempts),
            total_usage=TokenUsage(
                input_tokens=sum(item.input_tokens for item in usages),
                output_tokens=sum(item.output_tokens for item in usages),
            ),
            final_validation=validation,
            constraint_results=constraint_results,
        )
        draft_id = uuid5(
            NAMESPACE_URL,
            f"generated-draft:{value.request.request_id}:{value.retrieval.bundle_id}:{content}",
        )
        return GeneratedDraft(
            id=draft_id,
            request_id=value.request.request_id,
            content=content,
            thread=self._threads.split(content, value.request.platform),
            report=report,
            created_at=value.generated_at,
        )
