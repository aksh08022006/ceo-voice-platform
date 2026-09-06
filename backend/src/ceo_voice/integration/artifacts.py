"""Atomic, inspectable integration artifact persistence."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ceo_voice.integration.contracts import IntegrationOutcome


class ArtifactWriter:
    """Persist offline artifacts, or retain the caller's complete in-memory outcome.

    Filesystem storage is the default for CLI/batch integrations. HTTP/serverless callers
    explicitly select memory storage because their continuation already carries the outcome;
    serializing copies of every immutable profile into temporary files is unnecessary.
    """

    def __init__(self, *, storage: Literal["filesystem", "memory"] = "filesystem") -> None:
        self.storage = storage

    def write_model(self, root: Path, name: str, model: BaseModel) -> None:
        if self.storage == "memory":
            return
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{name}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(target)

    def write_outcome(self, outcome: IntegrationOutcome) -> None:
        if self.storage == "memory":
            return
        artifacts = outcome.artifacts
        for name, model in (
            ("voice-profile", artifacts.voice_profile),
            ("virality-profile", artifacts.virality_profile),
            ("generation-context", artifacts.context),
            ("retrieval-bundle", artifacts.retrieval),
            ("retrieval-ranking", artifacts.retrieval_ranking),
            ("rendered-prompt", artifacts.rendered_prompt),
            ("generated-draft", artifacts.draft),
        ):
            if model is not None:
                self.write_model(outcome.artifact_directory, name, model)
        if artifacts.draft is not None:
            self.write_model(
                outcome.artifact_directory,
                "output-validation",
                artifacts.draft.report.final_validation,
            )
            self.write_model(
                outcome.artifact_directory,
                "generation-report",
                artifacts.draft.report,
            )
        self.write_model(outcome.artifact_directory, "integration-outcome", outcome)
