"""Deterministic cross-artifact and generated-output validation."""

from ceo_voice.core.exceptions import GenerationError
from ceo_voice.generation.contracts import (
    GenerationInput,
    GenerationPolicy,
    OutputValidation,
    ValidationFinding,
)
from ceo_voice.generation.enums import ValidationCode
from ceo_voice.models.enums import Platform
from ceo_voice.prompts import THREAD_SEPARATOR


def validate_generation_input(value: GenerationInput) -> None:
    checks = (
        (
            value.request.request_id
            == value.context.intent.request_id
            == value.retrieval.intent.request_id,
            "request_mismatch",
        ),
        (
            value.request.tenant_id
            == value.context.intent.tenant_id
            == value.retrieval.intent.tenant_id,
            "tenant_mismatch",
        ),
        (
            value.request.ceo_id
            == value.context.intent.leader_id
            == value.retrieval.intent.leader_id,
            "leader_mismatch",
        ),
        (
            value.request.platform
            == value.context.platform.platform
            == value.retrieval.platform.platform,
            "platform_mismatch",
        ),
        (value.request.content_type == value.context.intent.content_type, "content_type_mismatch"),
        (
            value.request.thread_post_count == value.context.intent.thread_post_count,
            "thread_count_mismatch",
        ),
        (value.retrieval.source_context_id == value.context.context_id, "context_mismatch"),
        (
            value.retrieval.source_context_hash == value.context.content_hash,
            "context_hash_mismatch",
        ),
    )
    for valid, reason in checks:
        if not valid:
            raise GenerationError(
                "generation artifacts are incompatible", details={"reason": reason}
            )


class OutputValidator:
    """Enforce platform, safety, thread, explicit constraint, and confidence gates."""

    _UNSAFE = ("kill yourself", "racial slur")

    def validate(
        self, content: str, value: GenerationInput, policy: GenerationPolicy
    ) -> OutputValidation:
        posts = tuple(item.strip() for item in content.split(THREAD_SEPARATOR) if item.strip()) or (
            "",
        )
        findings: list[ValidationFinding] = []
        self._add(not content.strip(), ValidationCode.EMPTY, "output is empty", findings)
        if len(posts) > 1 and not value.context.platform.thread_output_supported:
            self._add(
                True,
                ValidationCode.THREAD_NOT_SUPPORTED,
                "platform does not support thread output",
                findings,
            )
        limit = value.context.platform.maximum_thread_posts
        if limit is not None:
            self._add(
                len(posts) > limit,
                ValidationCode.THREAD_LENGTH,
                "thread exceeds platform post count",
                findings,
            )
        requested_posts = value.request.thread_post_count
        if requested_posts is not None:
            self._add(
                len(posts) != requested_posts,
                ValidationCode.THREAD_POST_COUNT,
                f"thread must contain exactly {requested_posts} posts",
                findings,
            )
        for post in posts:
            character_count = len(post)
            maximum_characters = value.context.platform.maximum_characters
            self._add(
                character_count > maximum_characters,
                (
                    ValidationCode.THREAD_POST_LENGTH
                    if len(posts) > 1
                    else ValidationCode.PLATFORM_LENGTH
                ),
                (
                    f"post has {character_count} characters; rewrite it to at most "
                    f"{maximum_characters} characters"
                ),
                findings,
            )
        lowered = content.casefold()
        word_count = len(content.split())
        if value.request.minimum_words is not None:
            self._add(
                word_count < value.request.minimum_words,
                ValidationCode.WORD_COUNT,
                f"output must contain at least {value.request.minimum_words} words",
                findings,
            )
        if value.request.maximum_words is not None:
            self._add(
                word_count > value.request.maximum_words,
                ValidationCode.WORD_COUNT,
                f"output must contain at most {value.request.maximum_words} words",
                findings,
            )
        self._add(
            any(term in lowered for term in self._UNSAFE),
            ValidationCode.UNSAFE_CONTENT,
            "output contains blocked unsafe content",
            findings,
        )
        minimum = min(item.confidence.selection_score for item in value.retrieval.voice_features)
        self._add(
            minimum < policy.minimum_voice_confidence,
            ValidationCode.LOW_VOICE_CONFIDENCE,
            "voice target confidence is below generation policy",
            findings,
        )
        for constraint in value.request.constraints:
            if constraint.casefold().startswith("must include:"):
                required = constraint.split(":", 1)[1].strip()
                self._add(
                    required.casefold() not in lowered,
                    ValidationCode.REQUIRED_CONSTRAINT,
                    f"required phrase is missing: {required}",
                    findings,
                )
        return OutputValidation(
            valid=not any(item.blocking for item in findings),
            findings=tuple(findings),
            character_count=len(content),
            thread_posts=len(posts),
        )

    @staticmethod
    def _add(
        condition: bool, code: ValidationCode, message: str, findings: list[ValidationFinding]
    ) -> None:
        if condition:
            findings.append(ValidationFinding(code=code, message=message, blocking=True))


class ThreadGenerator:
    """Convert validated delimiter-based output into publishable platform units."""

    def split(self, content: str, platform: Platform) -> tuple[str, ...]:
        del platform
        return tuple(item.strip() for item in content.split(THREAD_SEPARATOR) if item.strip())
