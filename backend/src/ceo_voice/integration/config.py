"""Validated JSON loading for reproducible integration runs."""

from pathlib import Path

from ceo_voice.integration.contracts import IntegrationInput


def load_integration_input(path: Path) -> IntegrationInput:
    """Load a complete integration command without environment-dependent defaults."""

    return IntegrationInput.model_validate_json(path.read_text(encoding="utf-8"))
