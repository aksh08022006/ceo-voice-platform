"""Conservative, report-producing Re-Voice orchestration."""

from uuid import NAMESPACE_URL, uuid5

from ceo_voice.core.exceptions import ProviderError, ReVoiceValidationError
from ceo_voice.generation.contracts import ProviderRequest, TokenUsage
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.generation.validation import ThreadGenerator
from ceo_voice.prompts import THREAD_SEPARATOR
from ceo_voice.revoice.analysis import DifferenceAnalyzer, RegionDetector
from ceo_voice.revoice.contracts import (
    DifferenceAnalysis,
    PreservedDecision,
    RegionPlan,
    ReVoiceAttempt,
    ReVoicedDraft,
    ReVoiceInput,
    ReVoicePolicy,
    ReVoiceReport,
    ReVoiceValidation,
    VoiceFeatureStrengthening,
)
from ceo_voice.revoice.enums import ReVoiceAttemptKind, ReVoiceValidationCode
from ceo_voice.revoice.prompting import ReVoicePromptBuilder
from ceo_voice.revoice.validation import ReVoiceValidator, validate_revoice_input


class ReVoiceEngine:
    """Restore voice inside a deterministic edit envelope and fail closed on drift."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        policy: ReVoicePolicy,
        analyzer: DifferenceAnalyzer | None = None,
        detector: RegionDetector | None = None,
        prompts: ReVoicePromptBuilder | None = None,
        validator: ReVoiceValidator | None = None,
        threads: ThreadGenerator | None = None,
    ) -> None:
        if provider.name is not policy.provider:
            raise ValueError("provider and Re-Voice policy must agree")
        self._provider, self._policy = provider, policy
        self._analyzer = analyzer or DifferenceAnalyzer()
        self._detector = detector or RegionDetector()
        self._prompts = prompts or ReVoicePromptBuilder()
        self._validator = validator or ReVoiceValidator()
        self._threads = threads or ThreadGenerator()

    async def restore(self, value: ReVoiceInput) -> ReVoicedDraft:
        validate_revoice_input(value)
        difference = self._analyzer.analyze(
            value.edited_draft.baseline_content, value.edited_draft.content
        )
        regions = self._detector.detect(value.edited_draft.content, difference)
        preflight = self._validator.validate(
            value.edited_draft.content,
            value,
            regions,
            self._policy,
        )
        if not preflight.valid:
            raise self._human_edit_error(value, preflight)
        if not regions.editable:
            return self._no_call_result(value, difference, regions, preflight)
        attempts: list[ReVoiceAttempt] = []
        feedback: tuple[str, ...] = ()
        provider_failures = validation_failures = 0
        while True:
            system, user = self._prompts.build(value, regions, repair_feedback=feedback)
            estimated_tokens = max(
                1,
                int(len(system + "\n" + user) / self._policy.estimated_characters_per_token) + 1,
            )
            available_tokens = (
                self._policy.model_context_tokens - self._policy.maximum_output_tokens
            )
            if estimated_tokens > available_tokens:
                raise ReVoiceValidationError(
                    "mandatory Re-Voice guidance exceeds model context",
                    details={
                        "estimated_tokens": estimated_tokens,
                        "available_tokens": available_tokens,
                    },
                )
            kind = (
                ReVoiceAttemptKind.INITIAL
                if not attempts
                else (
                    ReVoiceAttemptKind.VALIDATION_REPAIR
                    if feedback
                    else ReVoiceAttemptKind.PROVIDER_RETRY
                )
            )
            try:
                result = await self._provider.generate(
                    ProviderRequest(
                        request_id=value.context.intent.request_id,
                        system=system,
                        user=user,
                        model=self._policy.model,
                        maximum_output_tokens=self._policy.maximum_output_tokens,
                    )
                )
            except ProviderError as error:
                attempts.append(
                    ReVoiceAttempt(
                        number=len(attempts) + 1,
                        kind=kind,
                        provider=self._policy.provider,
                        model=self._policy.model,
                        latency_ms=0,
                        usage=None,
                        validation=None,
                        error_code=error.code,
                    )
                )
                if (
                    not error.retryable
                    or provider_failures >= self._policy.maximum_provider_retries
                ):
                    raise
                provider_failures += 1
                feedback = ()
                continue
            candidate = result.text
            validation = self._validator.validate(candidate, value, regions, self._policy)
            attempts.append(
                ReVoiceAttempt(
                    number=len(attempts) + 1,
                    kind=kind,
                    provider=result.provider,
                    model=result.model,
                    latency_ms=result.latency_ms,
                    usage=result.usage,
                    validation=validation,
                )
            )
            if validation.valid:
                return self._result(value, difference, regions, candidate, tuple(attempts))
            if validation_failures >= self._policy.maximum_validation_retries:
                return self._safe_fallback(
                    value,
                    difference,
                    regions,
                    preflight,
                    tuple(attempts),
                )
            validation_failures += 1
            feedback = tuple(item.message for item in validation.findings if item.blocking)

    def _result(
        self,
        value: ReVoiceInput,
        difference: DifferenceAnalysis,
        regions: RegionPlan,
        content: str,
        attempts: tuple[ReVoiceAttempt, ...],
    ) -> ReVoicedDraft:
        validation = attempts[-1].validation
        if validation is None:  # pragma: no cover - result requires a validated attempt
            raise RuntimeError("validated Re-Voice attempt is missing validation")
        changed_regions = tuple(
            item.region_id
            for item in regions.editable
            if value.edited_draft.content.splitlines()[item.line_index]
            != content.splitlines()[item.line_index]
        )
        usages = tuple(item.usage for item in attempts if item.usage is not None)
        report = self._report(
            value, difference, regions, changed_regions, attempts, validation, usages
        )
        identifier = uuid5(
            NAMESPACE_URL,
            f"revoiced-draft:{value.edited_draft.original.id}:{value.retrieval.bundle_id}:{content}",
        )
        return ReVoicedDraft(
            id=identifier,
            original_draft_id=value.edited_draft.original.id,
            content=content,
            thread=self._threads.split(content, value.context.platform.platform),
            report=report,
            created_at=value.requested_at,
        )

    def _no_call_result(
        self,
        value: ReVoiceInput,
        difference: DifferenceAnalysis,
        regions: RegionPlan,
        validation: ReVoiceValidation,
    ) -> ReVoicedDraft:
        report = self._report(value, difference, regions, (), (), validation, ())
        content = value.edited_draft.content
        return ReVoicedDraft(
            id=uuid5(NAMESPACE_URL, f"revoiced-draft:{value.edited_draft.original.id}:{content}"),
            original_draft_id=value.edited_draft.original.id,
            content=content,
            thread=self._threads.split(content, value.context.platform.platform),
            report=report,
            created_at=value.requested_at,
        )

    def _safe_fallback(
        self,
        value: ReVoiceInput,
        difference: DifferenceAnalysis,
        regions: RegionPlan,
        validation: ReVoiceValidation,
        attempts: tuple[ReVoiceAttempt, ...],
    ) -> ReVoicedDraft:
        """Preserve a valid human edit when every model proposal violates the edit envelope."""

        usages = tuple(item.usage for item in attempts if item.usage is not None)
        report = self._report(
            value,
            difference,
            regions,
            (),
            attempts,
            validation,
            usages,
        )
        content = value.edited_draft.content
        return ReVoicedDraft(
            id=uuid5(
                NAMESPACE_URL,
                f"revoiced-draft:fallback:{value.edited_draft.original.id}:{content}",
            ),
            original_draft_id=value.edited_draft.original.id,
            content=content,
            thread=self._threads.split(content, value.context.platform.platform),
            report=report,
            created_at=value.requested_at,
        )

    @staticmethod
    def _human_edit_error(
        value: ReVoiceInput,
        validation: ReVoiceValidation,
    ) -> ReVoiceValidationError:
        """Return an actionable error for an invalid edit before spending provider tokens."""

        finding_codes = tuple(item.code.value for item in validation.findings)
        if ReVoiceValidationCode.PLATFORM_LENGTH.value in finding_codes:
            limit = value.context.platform.maximum_characters
            posts = tuple(
                item.strip()
                for item in value.edited_draft.content.split(THREAD_SEPARATOR)
                if item.strip()
            )
            longest = max((len(item) for item in posts), default=0)
            overage = max(0, longest - limit)
            platform = value.context.platform.platform.value.upper()
            return ReVoiceValidationError(
                f"The edited {platform} draft is {longest} characters—{overage} over the "
                f"{limit}-character limit. Shorten the human edit before Re-Voice; protected "
                "text will not be deleted automatically.",
                details={
                    "findings": finding_codes,
                    "platform": value.context.platform.platform.value,
                    "character_count": longest,
                    "maximum_characters": limit,
                    "characters_over": overage,
                },
            )
        return ReVoiceValidationError(
            "The human-edited draft violates a protected Re-Voice constraint.",
            details={"findings": finding_codes},
        )

    def _report(
        self,
        value: ReVoiceInput,
        difference: DifferenceAnalysis,
        regions: RegionPlan,
        changed_regions: tuple[str, ...],
        attempts: tuple[ReVoiceAttempt, ...],
        validation: ReVoiceValidation,
        usages: tuple[TokenUsage, ...],
    ) -> ReVoiceReport:
        voice = tuple(
            VoiceFeatureStrengthening(
                feature_id=item.feature_id,
                target=str(item.target_value),
                confidence=item.confidence.selection_score,
                assessment="targeted by the restoration prompt; not independently evaluated",
            )
            for item in value.retrieval.voice_features
            if changed_regions
        )
        protected_kinds = tuple(dict.fromkeys(item.kind.value for item in regions.protected))
        mean_voice = sum(item.confidence for item in voice) / len(voice) if voice else 1.0
        confidence = (
            max(0.0, min(1.0, mean_voice * (1 - validation.changed_fraction)))
            if changed_regions or not attempts
            else 0.0
        )
        hvm = value.voice_profile.managed_release.release
        vkr = value.virality_profile.publication.release
        return ReVoiceReport(
            engine_version=self._policy.version,
            prompt_version=self._policy.prompt_version,
            original_draft_id=value.edited_draft.original.id,
            context_id=value.context.context_id,
            retrieval_bundle_id=value.retrieval.bundle_id,
            hvm_release_id=hvm.id,
            vkr_release_id=vkr.id,
            difference=difference,
            regions=regions,
            changed_regions=changed_regions,
            preserved=tuple(
                PreservedDecision(subject=kind, reason="protected by deterministic region policy")
                for kind in protected_kinds
            ),
            voice_features_strengthened=voice,
            constrained_by=tuple(
                item.constraint_id for item in value.context.constraints.constraints
            ),
            attempts=attempts,
            total_usage=TokenUsage(
                input_tokens=sum(item.input_tokens for item in usages),
                output_tokens=sum(item.output_tokens for item in usages),
            ),
            total_latency_ms=sum(item.latency_ms for item in attempts),
            final_validation=validation,
            confidence=confidence,
        )
