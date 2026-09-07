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
from ceo_voice.generation.fidelity import FidelityReviewer, repair_feedback
from ceo_voice.generation.fidelity_contracts import FidelityReview
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
        fidelity_reviewer: FidelityReviewer | None = None,
    ) -> None:
        if provider.name is not policy.provider:
            raise ValueError("provider and generation policy must agree")
        if policy.fidelity.enabled and (
            fidelity_reviewer is None or fidelity_reviewer.policy != policy.fidelity
        ):
            raise ValueError("enabled fidelity policy requires a matching separate reviewer")
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
        self._fidelity_reviewer = fidelity_reviewer

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
                else (
                    AttemptKind.VALIDATION_REPAIR
                    if feedback and attempts[-1].error_code is None
                    else AttemptKind.PROVIDER_RETRY
                )
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
                continue
            validation = self._validator.validate(result.text, value, self._policy)
            fidelity_review: FidelityReview | None = None
            if validation.valid:
                content = self._post_processor.process(result.text)
                if self._policy.fidelity.enabled and self._fidelity_reviewer is not None:
                    fidelity_review = await self._fidelity_reviewer.review(content, value)
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
                    fidelity_review=fidelity_review,
                )
            )
            if fidelity_review is not None and fidelity_review.status == "error":
                if self._policy.fidelity.failure_behavior == "return_for_review":
                    break
                raise GenerationValidationError(
                    "brief fidelity review is unavailable; draft withheld",
                    details={"fidelity_review": fidelity_review.model_dump(mode="json")},
                )
            if validation.valid and (fidelity_review is None or fidelity_review.status == "clear"):
                break
            if not self._retry.repair_allowed(validation_failures):
                if (
                    validation.valid
                    and self._policy.fidelity.failure_behavior == "return_for_review"
                ):
                    break
                raise GenerationValidationError(
                    "provider could not produce a valid draft",
                    details={
                        "findings": [item.code.value for item in validation.findings],
                        "fidelity_review": (
                            fidelity_review.model_dump(mode="json") if fidelity_review else None
                        ),
                    },
                )
            validation_failures += 1
            feedback = tuple(item.message for item in validation.findings if item.blocking)
            if fidelity_review is not None:
                feedback += repair_feedback(fidelity_review)
        usages = tuple(item.usage for item in attempts if item.usage is not None)
        constraint_results = tuple(
            ConstraintResult(
                constraint_id=item.constraint_id,
                satisfied=None,
                detail="included in generation guidance; individual compiled constraint satisfaction is not independently verified",
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
            total_latency_ms=sum(
                item.latency_ms + (item.fidelity_review.latency_ms if item.fidelity_review else 0)
                for item in attempts
            ),
            total_usage=TokenUsage(
                input_tokens=sum(item.input_tokens for item in usages)
                + sum(
                    item.fidelity_review.input_tokens or 0
                    for item in attempts
                    if item.fidelity_review
                ),
                output_tokens=sum(item.output_tokens for item in usages)
                + sum(
                    item.fidelity_review.output_tokens or 0
                    for item in attempts
                    if item.fidelity_review
                ),
            ),
            final_validation=validation,
            constraint_results=constraint_results,
            fidelity_review=fidelity_review,
            generation_call_count=len(attempts),
            fidelity_call_count=sum(
                bool(item.fidelity_review and item.fidelity_review.provider_call_attempted)
                for item in attempts
            ),
            total_model_calls=len(attempts)
            + sum(
                bool(item.fidelity_review and item.fidelity_review.provider_call_attempted)
                for item in attempts
            ),
            maximum_generation_calls=1
            + self._policy.maximum_provider_retries
            + self._policy.maximum_validation_retries,
            maximum_fidelity_calls=(
                1 + self._policy.maximum_validation_retries if self._policy.fidelity.enabled else 0
            ),
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
