"""Fail-closed lineage, layout, protected-region, and constraint validation."""

import re
from difflib import SequenceMatcher

from ceo_voice.context.enums import ConstraintCategory, ConstraintOperator, ConstraintStrength
from ceo_voice.core.exceptions import ReVoiceError
from ceo_voice.prompts import THREAD_SEPARATOR
from ceo_voice.revoice.contracts import (
    RegionPlan,
    ReVoiceFinding,
    ReVoiceInput,
    ReVoicePolicy,
    ReVoiceValidation,
)
from ceo_voice.revoice.enums import ProtectionKind, ReVoiceValidationCode
from ceo_voice.virality.enums import PublicationStatus
from ceo_voice.voice.enums import ReleaseStatus

_FORMAT_PREFIX = re.compile(r"^(\s*(?:(?:[-*+>]\s+)|(?:#{1,6}\s+)|(?:\d+[.)]\s+))?)")
_INLINE_FORMAT = re.compile(r"\*\*|__|~~|(?<!`)`(?!`)")
_UNSAFE = ("kill yourself", "racial slur")


def validate_revoice_input(value: ReVoiceInput) -> None:
    """Require exact lineage across the edited draft and every sealed artifact."""

    voice_release = value.voice_profile.managed_release.release
    vkr_release = value.virality_profile.publication.release
    checks = (
        (value.edited_draft.original.request_id == value.context.intent.request_id, "request"),
        (
            value.edited_draft.original.report.retrieval_bundle_id == value.retrieval.bundle_id,
            "original_draft_retrieval",
        ),
        (value.retrieval.source_context_id == value.context.context_id, "context"),
        (value.retrieval.source_context_hash == value.context.content_hash, "context_hash"),
        (value.context.voice.release_id == voice_release.id, "hvm_release"),
        (value.context.voice.release_version == voice_release.version, "hvm_version"),
        (value.context.voice.release_content_hash == voice_release.content_hash, "hvm_hash"),
        (value.context.virality.release_id == vkr_release.id, "vkr_release"),
        (value.context.virality.release_version == vkr_release.version, "vkr_version"),
        (value.context.virality.release_content_hash == vkr_release.content_hash, "vkr_hash"),
        (value.context.intent.tenant_id == voice_release.tenant_id, "tenant"),
        (value.context.intent.leader_id == value.retrieval.intent.leader_id, "leader"),
        (value.context.platform.platform == value.retrieval.platform.platform, "platform"),
        (value.voice_profile.managed_release.status is ReleaseStatus.ACTIVE, "hvm_status"),
        (value.virality_profile.publication.status is PublicationStatus.ACTIVE, "vkr_status"),
    )
    for valid, boundary in checks:
        if not valid:
            raise ReVoiceError(
                "Re-Voice artifacts are incompatible", details={"boundary": boundary}
            )


class ReVoiceValidator:
    """Reject any proposal that escapes the deterministic edit envelope."""

    def validate(
        self,
        candidate: str,
        value: ReVoiceInput,
        regions: RegionPlan,
        policy: ReVoicePolicy,
    ) -> ReVoiceValidation:
        edited = value.edited_draft.content
        findings: list[ReVoiceFinding] = []
        self._add(not candidate.strip(), ReVoiceValidationCode.EMPTY, "output is empty", findings)
        self._add(
            any(ord(character) < 32 and character not in "\r\n\t" for character in candidate),
            ReVoiceValidationCode.INVALID_CONTROL_CHARACTER,
            "output contains an invalid control character",
            findings,
        )
        edited_lines, candidate_lines = edited.splitlines(), candidate.splitlines()
        self._add(
            self._newline_signature(edited) != self._newline_signature(candidate)
            or len(edited_lines) != len(candidate_lines),
            ReVoiceValidationCode.STRUCTURE_CHANGED,
            "paragraph, line, or thread structure changed",
            findings,
        )
        if len(edited_lines) == len(candidate_lines):
            self._add(
                any(
                    self._format_signature(before) != self._format_signature(after)
                    for before, after in zip(edited_lines, candidate_lines, strict=True)
                ),
                ReVoiceValidationCode.FORMATTING_CHANGED,
                "line-level formatting changed",
                findings,
            )
        violated_regions = self._violated_regions(candidate_lines, regions)
        self._add(
            bool(violated_regions),
            ReVoiceValidationCode.PROTECTED_TEXT_CHANGED,
            "one or more protected regions changed or moved",
            findings,
            violated_regions,
        )
        changed_fraction = 1 - SequenceMatcher(None, edited, candidate, autojunk=False).ratio()
        self._add(
            changed_fraction > policy.maximum_changed_fraction,
            ReVoiceValidationCode.CHANGE_BUDGET_EXCEEDED,
            "restoration changed more text than the conservative policy permits",
            findings,
        )
        posts = tuple(item.strip() for item in candidate.split(THREAD_SEPARATOR) if item.strip())
        self._add(
            any(len(item) > value.context.platform.maximum_characters for item in posts),
            ReVoiceValidationCode.PLATFORM_LENGTH,
            "a platform unit exceeds its character limit",
            findings,
        )
        maximum_posts = value.context.platform.maximum_thread_posts
        self._add(
            maximum_posts is not None and len(posts) > maximum_posts,
            ReVoiceValidationCode.THREAD_LENGTH,
            "thread exceeds its platform post limit",
            findings,
        )
        lowered = candidate.casefold()
        self._add(
            any(term in lowered for term in _UNSAFE),
            ReVoiceValidationCode.UNSAFE_CONTENT,
            "output contains blocked unsafe content",
            findings,
        )
        violated_constraints = self._hard_constraint_violations(candidate, value)
        self._add(
            bool(violated_constraints),
            ReVoiceValidationCode.HARD_CONSTRAINT_VIOLATED,
            "a deterministically enforceable hard constraint was violated",
            findings,
            violated_constraints,
        )
        preserved = len(regions.protected) - len(violated_regions)
        return ReVoiceValidation(
            valid=not any(item.blocking for item in findings),
            findings=tuple(findings),
            changed_fraction=changed_fraction,
            protected_regions_preserved=max(0, preserved),
            protected_regions_total=len(regions.protected),
        )

    @staticmethod
    def _newline_signature(content: str) -> tuple[str, ...]:
        return tuple(re.findall(r"\r\n|\n|\r", content))

    @staticmethod
    def _format_signature(line: str) -> tuple[str, tuple[str, ...]]:
        match = _FORMAT_PREFIX.match(line)
        prefix = match.group(1) if match else ""
        return prefix, tuple(_INLINE_FORMAT.findall(line))

    @staticmethod
    def _violated_regions(lines: list[str], regions: RegionPlan) -> tuple[str, ...]:
        violated: list[str] = []
        for region in regions.protected:
            if region.line_index >= len(lines):
                violated.append(region.region_id)
                continue
            line = lines[region.line_index]
            if region.kind in {ProtectionKind.UNCHANGED_TEXT, ProtectionKind.CTA}:
                changed = region.content != line
            else:
                changed = region.content not in line
            if changed:
                violated.append(region.region_id)
        return tuple(violated)

    @staticmethod
    def _hard_constraint_violations(candidate: str, value: ReVoiceInput) -> tuple[str, ...]:
        violations: list[str] = []
        for constraint in value.context.constraints.constraints:
            if constraint.strength is not ConstraintStrength.HARD:
                continue
            if constraint.category is ConstraintCategory.PLATFORM:
                continue
            if constraint.key == "output.character_count" and isinstance(
                constraint.value, (int, float)
            ):
                if (
                    constraint.operator is ConstraintOperator.MAXIMUM
                    and len(candidate) > int(constraint.value)
                ) or (
                    constraint.operator is ConstraintOperator.MINIMUM
                    and len(candidate) < int(constraint.value)
                ):
                    violations.append(constraint.constraint_id)
            elif constraint.operator is ConstraintOperator.PROHIBIT and isinstance(
                constraint.value, str
            ):
                if constraint.value.casefold() in candidate.casefold():
                    violations.append(constraint.constraint_id)
            elif (
                constraint.operator is ConstraintOperator.EQUALS
                and isinstance(constraint.value, str)
                and constraint.key.startswith("content.required")
                and constraint.value.casefold() not in candidate.casefold()
            ):
                violations.append(constraint.constraint_id)
        return tuple(violations)

    @staticmethod
    def _add(
        condition: bool,
        code: ReVoiceValidationCode,
        message: str,
        findings: list[ReVoiceFinding],
        region_ids: tuple[str, ...] = (),
    ) -> None:
        if condition:
            findings.append(
                ReVoiceFinding(code=code, message=message, blocking=True, region_ids=region_ids)
            )
