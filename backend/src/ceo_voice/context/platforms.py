"""Injected catalog for versioned publishing-platform contracts."""

from collections.abc import Iterable

from ceo_voice.context.contracts import PlatformContract
from ceo_voice.core.exceptions import ContextCompilationError
from ceo_voice.models.enums import Platform


class PlatformContractCatalog:
    """Resolve exact platform policy without process-global mutable state."""

    def __init__(self, contracts: Iterable[PlatformContract]) -> None:
        indexed: dict[Platform, PlatformContract] = {}
        for contract in contracts:
            if contract.platform in indexed:
                raise ValueError(f"duplicate platform contract: {contract.platform}")
            indexed[contract.platform] = contract
        if not indexed:
            raise ValueError("platform catalog requires at least one contract")
        self._contracts = indexed

    def get(self, platform: Platform) -> PlatformContract:
        """Return an exact contract or a stable unsupported-request error."""

        contract = self._contracts.get(platform)
        if contract is None:
            raise ContextCompilationError(
                "target platform is not supported by the context compiler",
                details={"reason": "unsupported_request", "platform": platform.value},
            )
        return contract
