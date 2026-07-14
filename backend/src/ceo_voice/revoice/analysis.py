"""Deterministic human-edit comparison and conservative region classification."""

import re
from difflib import SequenceMatcher

from ceo_voice.revoice.contracts import (
    DifferenceAnalysis,
    EditableRegion,
    ProtectedRegion,
    RegionPlan,
    TextChange,
)
from ceo_voice.revoice.enums import ChangeKind, ProtectionKind
from ceo_voice.utils.hashing import sha256_text

_PROTECTED_PATTERNS: tuple[tuple[ProtectionKind, re.Pattern[str]], ...] = (
    (ProtectionKind.MARKDOWN_LINK, re.compile(r"\[[^\]\n]+\]\(https?://[^)\s]+\)")),
    (ProtectionKind.URL, re.compile(r"https?://[^\s)]+")),
    (ProtectionKind.EMAIL, re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")),
    (ProtectionKind.SOCIAL_REFERENCE, re.compile(r"(?<!\w)[@#][\w.-]+")),
    (ProtectionKind.INLINE_CODE, re.compile(r"`[^`\n]+`")),
    (ProtectionKind.QUOTATION, re.compile(r'(?:"[^"\n]+"|“[^”\n]+”)')),
    (
        ProtectionKind.PROPER_NOUN,
        re.compile(r"\b[A-Z][\w.-]{2,}(?:\s+[A-Z][\w.-]+)*\b"),
    ),
    (
        ProtectionKind.NUMBER,
        re.compile(r"(?<!\w)(?:[$€£₹]\s*)?\d[\d,.]*(?:%|x|[kKmMbB])?(?!\w)"),
    ),
)
_CTA = re.compile(
    r"(?:\?|\b(?:reply|comment|share|follow|subscribe|join|read|try|tell me|let me know)\b)",
    re.IGNORECASE,
)


class DifferenceAnalyzer:
    """Record exact character-level changes and the edited lines they touched."""

    def analyze(self, original: str, edited: str) -> DifferenceAnalysis:
        matcher = SequenceMatcher(None, original, edited, autojunk=False)
        changes = tuple(
            TextChange(
                kind=ChangeKind(tag),
                original_start=i1,
                original_end=i2,
                edited_start=j1,
                edited_end=j2,
                original_text=original[i1:i2],
                edited_text=edited[j1:j2],
            )
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != ChangeKind.EQUAL.value
        )
        changed_lines: set[int] = set()
        line_matcher = SequenceMatcher(
            None, original.splitlines(), edited.splitlines(), autojunk=False
        )
        for tag, _i1, _i2, j1, j2 in line_matcher.get_opcodes():
            if tag in {ChangeKind.INSERT.value, ChangeKind.REPLACE.value}:
                changed_lines.update(range(j1, j2))
        return DifferenceAnalysis(
            original_hash=sha256_text(original),
            edited_hash=sha256_text(edited),
            similarity=matcher.ratio(),
            changes=changes,
            changed_line_indices=tuple(sorted(changed_lines)),
        )


class RegionDetector:
    """Allow restoration only on human-modified prose while protecting semantic anchors."""

    def detect(self, edited: str, difference: DifferenceAnalysis) -> RegionPlan:
        lines = edited.splitlines(keepends=True)
        changed = set(difference.changed_line_indices)
        editable: list[EditableRegion] = []
        protected: list[ProtectedRegion] = []
        offset = 0
        for line_index, raw_line in enumerate(lines):
            line = raw_line.rstrip("\r\n")
            line_start = offset
            line_end = line_start + len(line)
            offset += len(raw_line)
            if not line.strip():
                continue
            if line_index not in changed:
                protected.append(
                    self._protected(
                        line_index,
                        line_start,
                        line_end,
                        line,
                        ProtectionKind.UNCHANGED_TEXT,
                        "human did not edit this line",
                    )
                )
                continue
            editable.append(
                EditableRegion(
                    region_id=f"editable.line.{line_index}",
                    line_index=line_index,
                    start=line_start,
                    end=line_end,
                    content=line,
                    reason="line contains a human edit and may receive lexical voice restoration",
                )
            )
            occupied: list[tuple[int, int]] = []
            for kind, pattern in _PROTECTED_PATTERNS:
                for match in pattern.finditer(line):
                    if any(match.start() < end and match.end() > start for start, end in occupied):
                        continue
                    occupied.append((match.start(), match.end()))
                    protected.append(
                        self._protected(
                            line_index,
                            line_start + match.start(),
                            line_start + match.end(),
                            match.group(),
                            kind,
                            "factual or formatting-sensitive anchor",
                        )
                    )
            if _CTA.search(line):
                protected.append(
                    self._protected(
                        line_index,
                        line_start,
                        line_end,
                        line,
                        ProtectionKind.CTA,
                        "CTA wording and intent are preserved exactly",
                    )
                )
        return RegionPlan(editable=tuple(editable), protected=tuple(protected))

    @staticmethod
    def _protected(
        line_index: int,
        start: int,
        end: int,
        content: str,
        kind: ProtectionKind,
        reason: str,
    ) -> ProtectedRegion:
        return ProtectedRegion(
            region_id=f"protected.{kind.value}.{line_index}.{start}",
            line_index=line_index,
            start=start,
            end=end,
            content=content,
            kind=kind,
            reason=reason,
        )
