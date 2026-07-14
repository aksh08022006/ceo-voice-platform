"""Bounded retry decisions independent from generation orchestration."""

from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.contracts import GenerationPolicy


class RetryStrategy:
    """Keep transport retries and validation repairs independently bounded."""

    def __init__(self, policy: GenerationPolicy) -> None:
        self._policy = policy

    def provider_allowed(self, error: ProviderError, failures: int) -> bool:
        return error.retryable and failures < self._policy.maximum_provider_retries

    def repair_allowed(self, failures: int) -> bool:
        return failures < self._policy.maximum_validation_retries
