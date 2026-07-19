import { ProfileAnalyticsGovernance } from "@/components/profile-analytics-governance";
import {
  buildPlatformRows,
  ComparisonTable,
  DIMENSION_DESCRIPTIONS,
  ExplanationStep,
  formatDelta,
  formatFeatureValue,
  formatPercent,
  formatTarget,
  humanize,
  KEY_FEATURES,
  SectionHeading,
  Stat,
} from "@/components/profile-analytics-support";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { FeatureMetric, ProfileAnalytics } from "@/lib/api";

export function ProfileAnalyticsView({ analytics }: { analytics: ProfileAnalytics }) {
  const coreFeatures = analytics.features.filter((feature) => feature.scope === "core");
  const residualFeatures = analytics.features.filter(
    (feature) => feature.scope === "platform_residual",
  );
  const platformRows = buildPlatformRows(analytics.features);

  return (
    <div className="space-y-24 py-16">
      <EvidenceLedger
        analytics={analytics}
        coreFeatureCount={coreFeatures.length}
        residualFeatureCount={residualFeatures.length}
      />
      <HvmSemantics formula={analytics.hvm_formula} />
      <DimensionCoverage analytics={analytics} />
      <CoreMeasurements analytics={analytics} coreFeatures={coreFeatures} />
      <PlatformAdaptation rows={platformRows} />
      {analytics.comparisons.length > 0 ? (
        <section aria-labelledby="comparison-title">
          <SectionHeading
            eyebrow="Distinct profile targets"
            id="comparison-title"
            title="The leaders are not aliases for one generic persona"
            description="These are like-for-like core measurements compiled with the same feature definitions. Difference does not by itself prove author distinctiveness, but it verifies that the stored generation targets are measurably different."
          />
          <div className="mt-10 overflow-x-auto border-t border-border">
            <ComparisonTable comparisons={analytics.comparisons} />
          </div>
        </section>
      ) : null}
      <ProfileAnalyticsGovernance analytics={analytics} />
    </div>
  );
}

function EvidenceLedger({
  analytics,
  coreFeatureCount,
  residualFeatureCount,
}: {
  analytics: ProfileAnalytics;
  coreFeatureCount: number;
  residualFeatureCount: number;
}) {
  return (
    <section aria-labelledby="evidence-ledger-title">
      <SectionHeading
        eyebrow="Evidence ledger"
        id="evidence-ledger-title"
        title={`What ${analytics.corpus.total_documents.toLocaleString()} admitted posts produced`}
        description="These are counts from the exact content-addressed corpus used by this release. Observations are typed analyzer outputs; evidence units are immutable spans; feature families are the governed HVM measurements compiled from them."
      />
      <div className="mt-10 grid border-l border-t border-border sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Corpus documents" value={analytics.corpus.total_documents} />
        <Stat label="Words analyzed" value={analytics.corpus.total_words} />
        <Stat label="Typed observations" value={analytics.corpus.observation_count} />
        <Stat label="Unique evidence units" value={analytics.corpus.evidence_unit_count} />
        <Stat label="Core feature families" value={analytics.corpus.observed_feature_count} />
        <Stat label="HVM components" value={analytics.features.length} />
        <Stat label="Core measurements" value={coreFeatureCount} />
        <Stat label="Platform residuals" value={residualFeatureCount} />
      </div>
      <p className="mt-6 max-w-4xl text-xs leading-5 text-muted-foreground">
        {analytics.evidence_count_explanation}
      </p>
    </section>
  );
}

function HvmSemantics({ formula }: { formula: string }) {
  return (
    <section aria-labelledby="hvm-model-title" className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
      <div>
        <p className="eyebrow">HVM semantics</p>
        <h2
          className="mt-4 font-display text-4xl font-medium tracking-[-0.04em]"
          id="hvm-model-title"
        >
          One voice, modeled hierarchically.
        </h2>
        <p className="mt-6 max-w-xl text-sm leading-7 text-muted-foreground">
          HVM means Hierarchical Voice Model. It does not store a persona paragraph. It stores a
          governed leader-wide core and separate platform adjustments, each tied to typed
          observations and immutable evidence.
        </p>
        <div className="mt-8 border-l-2 border-primary pl-6 font-mono text-sm leading-7">
          {formula}
        </div>
      </div>
      <div className="border-t border-border">
        <ExplanationStep
          index="01"
          title="Evidence"
          body="Versioned document, paragraph, and sentence spans preserve where measurements came from."
        />
        <ExplanationStep
          index="02"
          title="Observations"
          body="Deterministic analyzers emit typed values for lexical, structural, rhetorical, tonal, and platform behavior."
        />
        <ExplanationStep
          index="03"
          title="Core behavior"
          body="Cross-platform measurements describe the leader's shared tendencies without collapsing them into prose."
        />
        <ExplanationStep
          index="04"
          title="Platform residuals"
          body="LinkedIn and X deltas adjust the core, preserving platform-specific pacing and formatting."
        />
        <ExplanationStep
          index="05"
          title="Governed release"
          body="The compiler pins the registry, evidence snapshot, observations, validation report, and content hash into an immutable version."
        />
      </div>
    </section>
  );
}

function DimensionCoverage({ analytics }: { analytics: ProfileAnalytics }) {
  return (
    <section aria-labelledby="dimensions-title">
      <SectionHeading
        eyebrow="Dimensional coverage"
        id="dimensions-title"
        title="What is actually represented"
        description="Coverage is measurement support within the admitted corpus. It is not a probability that a generated post was written by the leader."
      />
      <div className="mt-10 grid gap-x-10 border-t border-border md:grid-cols-2">
        {analytics.dimensions.map((dimension) => (
          <div className="border-b border-border py-7" key={dimension.dimension}>
            <div className="flex items-baseline justify-between gap-6">
              <h3 className="text-sm font-medium">{humanize(dimension.dimension)}</h3>
              <span className="font-mono text-xs text-muted-foreground">
                {dimension.core_feature_count} core / {dimension.total_component_count} total
              </span>
            </div>
            <p className="mt-2 min-h-10 text-xs leading-5 text-muted-foreground">
              {DIMENSION_DESCRIPTIONS[dimension.dimension] ??
                "A governed voice feature group in the published HVM registry."}
            </p>
            <div className="mt-5 flex items-center gap-4">
              <Progress value={dimension.average_coverage * 100} />
              <span className="w-12 text-right font-mono text-[11px] text-muted-foreground">
                {formatPercent(dimension.average_coverage)}
              </span>
            </div>
            <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              {dimension.support_links.toLocaleString()} feature-evidence links
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function CoreMeasurements({
  analytics,
  coreFeatures,
}: {
  analytics: ProfileAnalytics;
  coreFeatures: FeatureMetric[];
}) {
  const selected = KEY_FEATURES.map((featureId) =>
    coreFeatures.find((feature) => feature.feature_id === featureId),
  ).filter((feature): feature is FeatureMetric => feature !== undefined);
  return (
    <section aria-labelledby="measurements-title">
      <SectionHeading
        eyebrow="Core measurements"
        id="measurements-title"
        title={`What the corpus says about ${analytics.name}`}
        description="A selected set of direct HVM measurements. Values describe the admitted corpus and remain traceable to the complete component table below."
      />
      <div className="mt-10 overflow-x-auto border-t border-border">
        <table className="w-full min-w-[760px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
              <th className="py-4 pr-5 font-medium">Behavior</th>
              <th className="px-5 py-4 font-medium">HVM value</th>
              <th className="px-5 py-4 font-medium">Dimension</th>
              <th className="px-5 py-4 font-medium">Support links</th>
              <th className="py-4 pl-5 font-medium">State</th>
            </tr>
          </thead>
          <tbody>
            {selected.map((feature) => (
              <tr className="border-b border-border" key={feature.feature_id}>
                <td className="py-5 pr-5">
                  <p className="font-medium">{feature.display_name}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {feature.feature_id}
                  </p>
                </td>
                <td className="px-5 py-5 font-mono">
                  {formatFeatureValue(feature.value, feature.unit)}
                </td>
                <td className="px-5 py-5 text-muted-foreground">
                  {humanize(feature.dimension)}
                </td>
                <td className="px-5 py-5 font-mono text-muted-foreground">
                  {feature.support_count.toLocaleString()}
                </td>
                <td className="py-5 pl-5">
                  <Badge>{humanize(feature.decision_state)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PlatformAdaptation({ rows }: { rows: ReturnType<typeof buildPlatformRows> }) {
  return (
    <section aria-labelledby="platform-title">
      <SectionHeading
        eyebrow="Platform adaptation"
        id="platform-title"
        title="Core behavior is not copied unchanged to every platform"
        description="A residual is an adjustment relative to the leader-wide core. The effective target is shown only as deterministic arithmetic over the published core and platform delta."
      />
      <div className="mt-10 overflow-x-auto border-t border-border">
        <table className="w-full min-w-[980px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
              <th className="py-4 pr-4 font-medium">Feature</th>
              <th className="px-4 py-4 font-medium">Core</th>
              <th className="px-4 py-4 font-medium">LinkedIn Δ</th>
              <th className="px-4 py-4 font-medium">LinkedIn target</th>
              <th className="px-4 py-4 font-medium">X Δ</th>
              <th className="py-4 pl-4 font-medium">X target</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr className="border-b border-border" key={row.core.feature_id}>
                <td className="py-5 pr-4 font-medium">{row.core.display_name}</td>
                <td className="px-4 py-5 font-mono">
                  {formatFeatureValue(row.core.value, row.core.unit)}
                </td>
                <td className="px-4 py-5 font-mono text-muted-foreground">
                  {formatDelta(row.linkedin, row.core.unit)}
                </td>
                <td className="px-4 py-5 font-mono">{formatTarget(row.core, row.linkedin)}</td>
                <td className="px-4 py-5 font-mono text-muted-foreground">
                  {formatDelta(row.x, row.core.unit)}
                </td>
                <td className="py-5 pl-4 font-mono">{formatTarget(row.core, row.x)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
