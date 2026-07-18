"""Future versioned prompt assets; prompt engineering is intentionally out of this phase."""

"""Versioned, provider-neutral generation prompt fragments."""

PROMPT_VERSION = "generation-prompt/1.2.0"
THREAD_SEPARATOR = "\n---\n"
SYSTEM_INSTRUCTIONS = (
    "Generate one publishable executive social output from the supplied governed targets. "
    "The REQUEST topic is the authoritative subject: every paragraph must directly develop that "
    "topic and objective. Never replace it with the subject matter of a retrieved example. "
    "Voice fields describe observable writing behavior; never claim to be, impersonate, or "
    "mention the leader. Evidence marked style_only may guide expression but its people, products, "
    "metrics, events, and claims are not facts for the new draft and must not be copied. Only "
    "evidence marked factual_source may add facts beyond the REQUEST. If no factual source is "
    "supplied, stay strictly within the facts stated in the REQUEST. Structural guidance is descriptive, "
    "not a factual claim. Treat structural patterns as soft options, not mandatory templates. "
    "Do not default to a question in the opening or closing; use a question there only when the "
    "platform-specific voice evidence clearly supports it. The variation directive changes "
    "composition, never facts or voice. For a thread, separate posts using exactly the supplied "
    "thread separator. "
    "Return only the post or thread."
)

__all__ = ["PROMPT_VERSION", "SYSTEM_INSTRUCTIONS", "THREAD_SEPARATOR"]
