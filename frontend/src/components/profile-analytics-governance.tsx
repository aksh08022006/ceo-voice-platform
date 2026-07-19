"use client";

import { useMemo, useState } from "react";

import {
  Breakdown,
  FeatureTable,
  formatDate,
  humanize,
  LedgerRow,
  ReleaseField,
  SectionHeading,
} from "@/components/profile-analytics-support";
import { AccordionItem } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { FeatureMetric, ProfileAnalytics } from "@/lib/api";

export function ProfileAnalyticsGovernance({ analytics }: { analytics: ProfileAnalytics }) {
  return (
    <>
      <CorpusProvenance analytics={analytics} />
      <ReleaseGovernance analytics={analytics} />
      <CompleteFeatureInspection features={analytics.features} />
      <TrustBoundary analytics={analytics} />
    </>
  );
}

function CorpusProvenance({ analytics }: { analytics: ProfileAnalytics }) {
  return (
    <section aria-labelledby="provenance-title" className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
      <div>
        <p className="eyebrow">Corpus provenance</p>
        <h2
          className="mt-4 font-display text-4xl font-medium tracking-[-0.04em]"
          id="provenance-title"
        >
          What entered the model—and what did not.
        </h2>
        <p className="mt-6 max-w-xl text-sm leading-7 text-muted-foreground">
          This ledger describes the admitted source envelopes. It makes manual acquisition,
          uncertainty, missing dates, and development-only authority visible instead of hiding
          those limitations behind a model score.
        </p>
      </div>
      <div className="border-t border-border">
        <Breakdown label="Platforms" values={analytics.corpus.platforms} />
        <Breakdown label="Sources" values={analytics.corpus.sources} />
        <Breakdown label="Content types" values={analytics.corpus.content_types} />
        <Breakdown label="Document types" values={analytics.corpus.document_types} />
        <Breakdown label="Source modalities" values={analytics.corpus.source_modalities} />
        <Breakdown label="Acquisition methods" values={analytics.corpus.acquisition_methods} />
        <Breakdown label="Capture media" values={analytics.corpus.capture_media} />
        <Breakdown label="Languages" values={analytics.corpus.languages} />
        <Breakdown label="Evidence segmentation" values={analytics.corpus.evidence_unit_types} />
        <LedgerRow label="Reposts" value={analytics.corpus.reposts.toLocaleString()} />
        <LedgerRow label="Quote posts" value={analytics.corpus.quote_posts.toLocaleString()} />
        <LedgerRow
          label="Documents with uncertain spans"
          value={analytics.corpus.uncertain_documents.toLocaleString()}
        />
        <LedgerRow
          label="Exact publication dates"
          value={`${analytics.corpus.exact_publication_dates} / ${analytics.corpus.total_documents}`}
        />
        <LedgerRow
          label="Development-only documents"
          value={`${analytics.corpus.development_only_documents} / ${analytics.corpus.total_documents}`}
        />
        <LedgerRow
          label="Analyzer failures"
          value={analytics.corpus.failed_analyzers.toLocaleString()}
        />
      </div>
    </section>
  );
}

function ReleaseGovernance({ analytics }: { analytics: ProfileAnalytics }) {
  return (
    <section aria-labelledby="release-title">
      <SectionHeading
        eyebrow="Release governance"
        id="release-title"
        title={`Immutable HVM release v${analytics.release.version}`}
        description={analytics.release.summary}
      />
      <div className="mt-10 grid border-l border-t border-border md:grid-cols-2">
        <ReleaseField label="Release ID" value={analytics.release.release_id} />
        <ReleaseField label="Content hash" value={analytics.release.content_hash} />
        <ReleaseField label="Corpus hash" value={analytics.corpus.corpus_hash} />
        <ReleaseField label="Registry hash" value={analytics.release.registry_hash} />
        <ReleaseField label="Lifecycle status" value={analytics.release.status} />
        <ReleaseField label="Artifact status" value={analytics.release.artifact_status} />
        <ReleaseField label="Scientific authority" value={analytics.release.authority} />
        <ReleaseField
          label="Structural validation"
          value={analytics.release.structurally_valid ? "passed" : "failed"}
        />
        <ReleaseField label="Registry version" value={analytics.release.registry_version} />
        <ReleaseField label="Compiler version" value={analytics.release.compiler_version} />
        <ReleaseField label="Validator version" value={analytics.release.validator_version} />
        <ReleaseField
          label="Validation findings"
          value={analytics.release.validation_issue_count.toString()}
        />
        <ReleaseField
          label="Lifecycle events"
          value={analytics.release.lifecycle_event_count.toString()}
        />
        <ReleaseField label="Sealed at" value={formatDate(analytics.release.created_at)} />
        <ReleaseField label="Published at" value={formatDate(analytics.release.published_at)} />
        <ReleaseField label="Inspected at" value={formatDate(analytics.release.inspected_at)} />
      </div>
    </section>
  );
}

function CompleteFeatureInspection({ features }: { features: FeatureMetric[] }) {
  const [featureQuery, setFeatureQuery] = useState("");
  const filteredDimensions = useMemo(() => {
    const query = featureQuery.trim().toLocaleLowerCase();
    const grouped = new Map<string, FeatureMetric[]>();
    for (const feature of features) {
      const searchable =
        `${feature.display_name} ${feature.feature_id} ${feature.dimension} ${feature.unit}`.toLocaleLowerCase();
      if (query && !searchable.includes(query)) continue;
      const items = grouped.get(feature.dimension) ?? [];
      items.push(feature);
      grouped.set(feature.dimension, items);
    }
    return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [features, featureQuery]);

  return (
    <section aria-labelledby="all-features-title">
      <SectionHeading
        eyebrow="Complete component inspection"
        id="all-features-title"
        title={`All ${features.length} published scalar components`}
        description="Search by behavior, feature identifier, unit, or dimension. Each core component and each platform residual is shown with its exact version, value, support, coverage, and decision state."
      />
      <div className="mt-8 max-w-xl">
        <label className="sr-only" htmlFor="feature-search">
          Search HVM components
        </label>
        <Input
          id="feature-search"
          onChange={(event) => setFeatureQuery(event.target.value)}
          placeholder="Search sentence length, emoji, rhetoric…"
          type="search"
          value={featureQuery}
        />
      </div>
      <div className="mt-8 border-t border-border">
        {filteredDimensions.length > 0 ? (
          filteredDimensions.map(([dimension, dimensionFeatures], index) => (
            <AccordionItem
              defaultOpen={index === 0 && featureQuery.length > 0}
              key={dimension}
              title={`${humanize(dimension)} · ${dimensionFeatures.length} components`}
            >
              <FeatureTable features={dimensionFeatures} />
            </AccordionItem>
          ))
        ) : (
          <p className="border-b border-border py-10 text-sm text-muted-foreground">
            No HVM component matches “{featureQuery}”.
          </p>
        )}
      </div>
    </section>
  );
}

function TrustBoundary({ analytics }: { analytics: ProfileAnalytics }) {
  const additionalLimitations = analytics.limitations.filter(
    (limitation) => !analytics.corpus.issues.some((issue) => issue.message === limitation),
  );
  return (
    <section
      aria-labelledby="trust-title"
      className="grid gap-12 border-y border-border py-14 lg:grid-cols-[0.8fr_1.2fr]"
    >
      <div>
        <p className="eyebrow">Trust boundary</p>
        <h2
          className="mt-4 font-display text-4xl font-medium tracking-[-0.04em]"
          id="trust-title"
        >
          What this evidence proves—and what it cannot.
        </h2>
        <div className="mt-7 flex flex-wrap gap-2">
          <Badge>{analytics.corpus.health_status}</Badge>
          <Badge>{analytics.release.authority} authority</Badge>
          <Badge>{analytics.release.structurally_valid ? "structure valid" : "invalid"}</Badge>
        </div>
      </div>
      <div>
        <p className="text-base leading-8">{analytics.trust_statement}</p>
        <div className="mt-8 space-y-4">
          {analytics.corpus.issues.map((issue) => (
            <div className="border-l-2 border-border pl-5" key={issue.code}>
              <div className="flex items-center gap-3">
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  {humanize(issue.code)}
                </p>
                <Badge>{issue.blocking ? "blocking" : "disclosed"}</Badge>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{issue.message}</p>
            </div>
          ))}
          {additionalLimitations.map((limitation) => (
            <p
              className="border-l-2 border-border pl-5 text-sm text-muted-foreground"
              key={limitation}
            >
              {limitation}
            </p>
          ))}
        </div>
        <div className="mt-10 border-t border-border pt-8 text-sm leading-7 text-muted-foreground">
          <p>
            <strong className="font-medium text-foreground">Structural validation</strong> checks
            release integrity, registry pins, evidence references, and internal consistency.
          </p>
          <p className="mt-3">
            <strong className="font-medium text-foreground">Fidelity validation</strong> requires
            held-out posts, blinded human review, cohort distinctiveness tests, and longitudinal
            data. Those results should be added as separate evidence—not folded into a cosmetic
            percentage.
          </p>
        </div>
      </div>
    </section>
  );
}
