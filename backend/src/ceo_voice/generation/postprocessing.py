"""Conservative cleanup after validation; never rewrite voice-bearing text."""

from ceo_voice.core.exceptions import GenerationValidationError


class PostProcessor:
    """Normalize transport artifacts without stylistic rewriting."""

    def process(self, content: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if "\x00" in normalized:
            raise GenerationValidationError("generated output contains invalid control characters")
        return normalized
