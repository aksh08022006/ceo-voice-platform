"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { draftTextSegments, exactSpan, publicSourceUrl } from "@/lib/editor-spans";
import type { ClaimState, DraftReviewGate, DraftRevision, EditorActor, EditorBrief, EditorSource } from "@/lib/editor-types";

const claimLabels: Record<ClaimState, string> = {
  supported: "Support found",
  unsupported: "Unsupported · blocks approval",
  contradicted: "Contradicted · blocks approval",
  uncertain: "Uncertain · blocks approval",
};

type ClaimReviewPanelProps = {
  brief: EditorBrief;
  revision: DraftRevision;
  review: DraftReviewGate;
  actor: EditorActor;
};

export function ClaimReviewPanel(props: ClaimReviewPanelProps) {
  return <ClaimReviewBody {...props} key={`${props.revision.id}:${props.review.review_run_id}`} />;
}

function ClaimReviewBody({ brief, revision, review }: ClaimReviewPanelProps) {
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const selected = review.claims.find((claim) => claim.id === selectedClaimId) ?? null;
  const reviewMatches = review.revision_id === revision.id && review.content_sha256 === revision.content_sha256 && review.brief_sha256 === brief.content_sha256;
  const located = selected && selected.revision_id === revision.id ? exactSpan(revision.content, selected.span) : null;
  return <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,.85fr)]">
    <section>
      <h2 className="font-display text-2xl font-medium">Read the exact draft</h2>
      <p className="mt-2 text-sm text-muted-foreground">Select a claim to see its words in context and the source used to assess it.</p>
      <article className="mt-5 whitespace-pre-wrap border-y border-border py-6 font-display text-lg leading-8" aria-label={`Draft version ${revision.number}`}>
        {draftTextSegments(revision.content, reviewMatches && located && selected ? selected.span : null).map((segment, index) => segment.highlighted ? <mark className="rounded-sm bg-primary/20 text-foreground" key={index}>{segment.text}</mark> : <span key={index}>{segment.text}</span>)}
      </article>
      {!reviewMatches ? <p className="mt-4 text-sm text-destructive" role="alert">These findings belong to an earlier version. Run review again before using them.</p> : null}
      {selected && !located ? <p className="mt-4 text-sm text-destructive" role="alert">The claim location does not match this draft. Review the complete text and rerun the check.</p> : null}
      <SourceBrief brief={brief} />
    </section>
    <section aria-label="Claim findings">
      <h2 className="font-display text-2xl font-medium">Claims and evidence</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">Automated findings guide review. Support found for a claim is not approval of the draft.</p>
      {review.state === "review_pending" ? <p className="mt-6 text-sm" role="status">Run claim review to check this saved version.</p> : null}
      {review.state === "unavailable" ? <p className="mt-6 text-sm" role="alert">No complete claim review is available. Approval remains blocked.</p> : null}
      {review.claims.length === 0 && review.state !== "review_pending" && review.state !== "unavailable" ? <p className="mt-6 text-sm text-muted-foreground">No claim findings were returned. Read the complete draft before recording a decision.</p> : null}
      <ol className="mt-5 divide-y divide-border">
        {review.claims.map((claim, index) => <li className="py-5" key={claim.id}>
          <button type="button" className="w-full rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-pressed={selectedClaimId === claim.id} onClick={() => setSelectedClaimId(claim.id)}>
            <span className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs"><span>Claim {index + 1}</span><Badge>{claimLabels[claim.state]}</Badge></span>
            <blockquote className="whitespace-pre-wrap text-sm font-medium leading-6">{claim.span.text}</blockquote>
          </button>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{claim.reason}</p>
          {claim.citations.map((citation, citationIndex) => {
            const source = brief.sources.find((item) => item.id === citation.source_id);
            const match = source ? exactSpan(source.text, citation.span) : null;
            return source && match ? <div className="mt-4 border-s-2 border-border ps-3" key={`${citation.source_id}:${citationIndex}`}><SourceLink source={source} /><blockquote className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted-foreground">{match.selected}</blockquote></div> : <p className="mt-3 text-xs text-destructive" key={`${citation.source_id}:${citationIndex}`}>The cited source excerpt is unavailable or does not match. Check the original source.</p>;
          })}
          {claim.state === "uncertain" ? <p className="mt-4 text-xs text-muted-foreground">Revise this claim or supply clearer evidence in a new brief, then run review again.</p> : null}
        </li>)}
      </ol>
    </section>
  </div>;
}

export function SourceBrief({ brief }: { brief: EditorBrief }) {
  return <section className="mt-8" aria-label="Exact source brief">
    <h3 className="font-display text-xl font-medium">Source brief</h3>
    <p className="mt-4 whitespace-pre-wrap text-sm leading-7">{brief.idea}</p>
    {brief.constraints.length ? <ul className="mt-4 list-disc space-y-2 ps-5 text-sm leading-6">{brief.constraints.map((constraint, index) => <li key={index}>{constraint}</li>)}</ul> : null}
    {brief.parent_post ? <details className="mt-4 border-y border-border py-3"><summary className="cursor-pointer text-sm font-medium">Parent post · {brief.reply_intent?.replaceAll("_", " ")}</summary><blockquote className="mt-4 whitespace-pre-wrap border-s-2 border-border ps-3 text-sm leading-6">{brief.parent_post}</blockquote></details> : null}
    <div className="mt-4 divide-y divide-border">{brief.sources.map((source) => <details className="py-4" key={source.id}><summary className="cursor-pointer text-sm font-medium">{source.title}</summary><div className="mt-3"><SourceLink source={source} />{source.attribution ? <p className="mt-2 text-xs text-muted-foreground">{source.attribution}</p> : null}<blockquote className="mt-3 whitespace-pre-wrap border-s-2 border-border ps-3 text-sm leading-6">{source.text}</blockquote></div></details>)}</div>
  </section>;
}

function SourceLink({ source }: { source: EditorSource }) {
  const url = publicSourceUrl(source.url);
  return url ? <a className="text-xs font-medium text-primary underline underline-offset-4" href={url} target="_blank" rel="noreferrer">{source.title}</a> : <span className="text-xs font-medium">{source.title}</span>;
}
