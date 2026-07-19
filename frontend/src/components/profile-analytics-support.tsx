import type { ReactNode } from "react";

import type { CountBreakdown, FeatureComparison, FeatureMetric } from "@/lib/api";

export const KEY_FEATURES = [
  "analysis.word-count",
  "analysis.mean-sentence-words",
  "analysis.paragraph-count",
  "analysis.opening-first-person-indicator",
  "analysis.opening-question-indicator",
  "analysis.closing-question-indicator",
  "analysis.emoji-count",
  "analysis.exclamation-frequency",
  "analysis.certainty-marker-rate",
  "analysis.hedge-marker-rate",
];

export const DIMENSION_DESCRIPTIONS: Record<string, string> = {
  audience_interpersonal: "How the writer addresses, includes, and relates to the audience.",
  discourse_rhetorical: "Openings, closings, transitions, questions, and rhetorical sequencing.",
  layout: "Paragraphs, line breaks, lists, links, and visual organization.",
  lexical: "Vocabulary diversity, pronoun choices, function words, and word-level preferences.",
  narrative_perspective: "First-person positioning and the writer's point of view.",
  orthographic: "Capitalization, punctuation, hashtags, mentions, and emoji behavior.",
  platform_adaptation: "Formatting signals that change between LinkedIn and X.",
  pragmatic_stance: "Certainty, hedging, conviction, and qualification.",
  reasoning_argument: "How causal and argumentative relationships are expressed.",
  rhythmic: "Sentence and paragraph length, variation, pacing, and repetition.",
};

export type PlatformRow = {
  core: FeatureMetric;
  linkedin?: FeatureMetric;
  x?: FeatureMetric;
};

export function SectionHeading({
  eyebrow,
  id,
  title,
  description,
}: {
  eyebrow: string;
  id: string;
  title: string;
  description: string;
}) {
  return (
    <div className="max-w-4xl">
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-4 font-display text-4xl font-medium tracking-[-0.04em] sm:text-5xl" id={id}>
        {title}
      </h2>
      <p className="mt-5 max-w-3xl text-sm leading-7 text-muted-foreground">{description}</p>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-b border-r border-border p-6">
      <p className="font-display text-3xl font-medium tracking-[-0.04em]">
        {value.toLocaleString()}
      </p>
      <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </p>
    </div>
  );
}

export function ExplanationStep({
  index,
  title,
  body,
}: {
  index: string;
  title: string;
  body: string;
}) {
  return (
    <div className="grid gap-3 border-b border-border py-6 sm:grid-cols-[2.5rem_10rem_1fr]">
      <span className="font-mono text-[10px] text-muted-foreground">{index}</span>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}

export function ComparisonTable({ comparisons }: { comparisons: FeatureComparison[] }) {
  const selected = KEY_FEATURES.map((featureId) =>
    comparisons.find((comparison) => comparison.feature_id === featureId),
  ).filter((comparison): comparison is FeatureComparison => comparison !== undefined);
  const leaders = selected[0]?.values ?? [];
  return (
    <table className="w-full min-w-[720px] border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
          <th className="py-4 pr-5 font-medium">Core behavior</th>
          {leaders.map((leader) => (
            <th className="px-5 py-4 font-medium" key={leader.profile_slug}>
              {leader.profile_name}
            </th>
          ))}
          <th className="py-4 pl-5 font-medium">Interpretation</th>
        </tr>
      </thead>
      <tbody>
        {selected.map((comparison) => (
          <tr className="border-b border-border" key={comparison.feature_id}>
            <td className="py-5 pr-5 font-medium">{comparison.display_name}</td>
            {comparison.values.map((value) => (
              <td className="px-5 py-5 font-mono" key={value.profile_slug}>
                {formatFeatureValue(value.value, comparison.unit)}
              </td>
            ))}
            <td className="py-5 pl-5 text-xs leading-5 text-muted-foreground">
              {comparisonInterpretation(comparison)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function FeatureTable({ features }: { features: FeatureMetric[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-border font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">
            <th className="py-3 pr-4 font-medium">Component</th>
            <th className="px-4 py-3 font-medium">Scope</th>
            <th className="px-4 py-3 font-medium">Value</th>
            <th className="px-4 py-3 font-medium">Coverage</th>
            <th className="px-4 py-3 font-medium">Support</th>
            <th className="py-3 pl-4 font-medium">Version / state</th>
          </tr>
        </thead>
        <tbody>
          {features.map((feature) => (
            <tr
              className="border-b border-border/70"
              key={`${feature.feature_id}-${feature.platform ?? "core"}`}
            >
              <td className="py-4 pr-4">
                <p className="font-medium text-foreground">{feature.display_name}</p>
                <p className="mt-1 font-mono text-[9px] text-muted-foreground">
                  {feature.feature_id}
                </p>
              </td>
              <td className="px-4 py-4">
                {feature.scope === "core"
                  ? "Leader core"
                  : `${humanize(feature.platform ?? "")} residual`}
              </td>
              <td className="px-4 py-4 font-mono text-foreground">
                {formatFeatureValue(feature.value, feature.unit)}
              </td>
              <td className="px-4 py-4 font-mono">
                {formatPercent(feature.confidence_coverage)}
              </td>
              <td className="px-4 py-4 font-mono">
                {feature.support_count.toLocaleString()}
              </td>
              <td className="py-4 pl-4">
                <span className="font-mono">v{feature.version}</span>
                <span className="ml-2 text-muted-foreground">
                  {humanize(feature.decision_state)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Breakdown({ label, values }: { label: string; values: CountBreakdown[] }) {
  return (
    <div className="grid gap-3 border-b border-border py-5 sm:grid-cols-[13rem_1fr]">
      <p className="text-sm font-medium">{label}</p>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        {values.map((value) => (
          <span className="font-mono text-xs text-muted-foreground" key={value.label}>
            {humanize(value.label)}{" "}
            <strong className="font-medium text-foreground">{value.count}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

export function LedgerRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-3 border-b border-border py-5 sm:grid-cols-[13rem_1fr]">
      <p className="text-sm font-medium">{label}</p>
      <p className="font-mono text-xs text-muted-foreground">{value}</p>
    </div>
  );
}

export function ReleaseField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 border-b border-r border-border p-6">
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-3 break-all font-mono text-xs leading-5">{value}</p>
    </div>
  );
}

export function buildPlatformRows(features: FeatureMetric[]): PlatformRow[] {
  const rows = new Map<string, PlatformRow>();
  for (const feature of features) {
    if (feature.scope === "core") rows.set(feature.feature_id, { core: feature });
  }
  for (const feature of features) {
    if (feature.scope !== "platform_residual") continue;
    const row = rows.get(feature.feature_id);
    if (!row) continue;
    if (feature.platform === "linkedin") row.linkedin = feature;
    if (feature.platform === "x") row.x = feature;
  }
  return KEY_FEATURES.map((featureId) => rows.get(featureId)).filter(
    (row): row is PlatformRow =>
      row !== undefined && (row.linkedin !== undefined || row.x !== undefined),
  );
}

export function formatTarget(core: FeatureMetric, residual?: FeatureMetric): string {
  if (!residual) return "—";
  return formatFeatureValue(core.value + residual.value, core.unit);
}

export function formatDelta(feature: FeatureMetric | undefined, unit: string): string {
  if (!feature) return "—";
  const prefix = feature.value > 0 ? "+" : "";
  if (isRatioUnit(unit)) return `${prefix}${(feature.value * 100).toFixed(1)} pp`;
  return `${prefix}${formatFeatureValue(feature.value, unit)}`;
}

export function formatFeatureValue(value: number, unit: string): string {
  if (isRatioUnit(unit)) return `${(value * 100).toFixed(1)}%`;
  const formatted = Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2);
  return `${formatted.replace(/\.00$/, "")} ${humanize(unit)}`;
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

function isRatioUnit(unit: string): boolean {
  return unit === "ratio" || unit === "binary" || unit === "normalized_position";
}

function comparisonInterpretation(comparison: FeatureComparison): string {
  if (comparison.values.length < 2) return "Insufficient peer coverage.";
  const sorted = [...comparison.values].sort((left, right) => right.value - left.value);
  const direction = isRatioUnit(comparison.unit)
    ? "higher measured rate"
    : "higher corpus average";
  return `${sorted[0].profile_name} has the ${direction}; this is descriptive, not a causal or identity claim.`;
}
