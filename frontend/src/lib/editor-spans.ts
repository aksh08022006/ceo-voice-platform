import type { ReviewSpan } from "./editor-types";

export type DraftTextSegment = { text: string; highlighted: boolean };

/** Offsets use Unicode code points, not JavaScript's UTF-16 code units. */
export function exactSpan(text: string, span: ReviewSpan): { before: string; selected: string; after: string } | null {
  const characters = Array.from(text);
  if (
    span.offset_unit !== "unicode_code_points" ||
    !Number.isSafeInteger(span.start) || !Number.isSafeInteger(span.end) ||
    span.start < 0 || span.end <= span.start || span.end > characters.length
  ) return null;
  const selected = characters.slice(span.start, span.end).join("");
  if (selected !== span.text) return null;
  return {
    before: characters.slice(0, span.start).join(""),
    selected,
    after: characters.slice(span.end).join(""),
  };
}

export function draftTextSegments(text: string, span: ReviewSpan | null): DraftTextSegment[] {
  const located = span ? exactSpan(text, span) : null;
  return located
    ? [
        { text: located.before, highlighted: false },
        { text: located.selected, highlighted: true },
        { text: located.after, highlighted: false },
      ]
    : [{ text, highlighted: false }];
}

export function publicSourceUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}
