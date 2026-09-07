"""Bounded retry decisions independent from generation orchestration."""

from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.contracts import GenerationPolicy


class RetryStrategy:
    """Keep transport retries and validation repairs independently bounded."""

    def __init__(self, policy: GenerationPolicy) -> None:
        self._policy = policy

    def provider_allowed(self, error: ProviderError, failures: int) -> bool:
        return (
            error.retryable
            and failures < self._policy.maximum_provider_retries
            and self.delay_seconds(error, failures) <= 60
        )

    def delay_seconds(self, error: ProviderError, failures: int) -> float:
        specified = error.details.get("retry_after_seconds")
        if isinstance(specified, (float, int)) and specified >= 0:
            return float(specified)
        status = error.details.get("status_code")
        if status == 429:
            return float(min(10 * 2**failures, 60))
        if isinstance(status, int) and status >= 500:
            return float(min(2**failures, 8))
        return 0.0

    def repair_allowed(self, failures: int) -> bool:
        return failures < self._policy.maximum_validation_retries
