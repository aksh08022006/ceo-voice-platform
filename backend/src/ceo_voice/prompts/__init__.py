"""Future versioned prompt assets; prompt engineering is intentionally out of this phase."""

"""Versioned, provider-neutral generation prompt fragments."""

PROMPT_VERSION = "generation-prompt/1.1.0"
THREAD_SEPARATOR = "\n---\n"
SYSTEM_INSTRUCTIONS = (
    "Generate one publishable executive social output from the supplied governed targets. "
    "Voice fields describe observable writing behavior; never claim to be, impersonate, or "
    "mention the leader. Use only supplied factual evidence. Structural guidance is descriptive, "
    "not a factual claim. Treat structural patterns as soft options, not mandatory templates. "
    "Do not default to a question in the opening or closing; use a question there only when the "
    "platform-specific voice evidence clearly supports it. The variation directive changes "
    "composition, never facts or voice. For a thread, separate posts using exactly the supplied "
    "thread separator. "
    "Return only the post or thread."
)

__all__ = ["PROMPT_VERSION", "SYSTEM_INSTRUCTIONS", "THREAD_SEPARATOR"]
