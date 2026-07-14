"""Future versioned prompt assets; prompt engineering is intentionally out of this phase."""

"""Versioned, provider-neutral generation prompt fragments."""

PROMPT_VERSION = "generation-prompt/1.0.0"
THREAD_SEPARATOR = "\n---\n"
SYSTEM_INSTRUCTIONS = (
    "Generate one publishable executive social post from the supplied governed targets. "
    "Voice fields describe observable writing behavior; never claim to be, impersonate, or "
    "mention the leader. Use only supplied factual evidence. Structural guidance is descriptive, "
    "not a factual claim. Return only the post."
)

__all__ = ["PROMPT_VERSION", "SYSTEM_INSTRUCTIONS", "THREAD_SEPARATOR"]
