# Governed Corpus Acquisition

Voice quality begins with evidence quality. This workflow separates source discovery from content
acquisition so the system can answer three different questions independently:

1. Does a source exist and belong to the intended leader?
2. May the operator acquire and retain it using the recorded method?
3. Is its content valid evidence of the leader's voice?

A public URL is not, by itself, permission to scrape or evidence of authorship. The committed
catalog therefore contains URLs and governance metadata only. Source text, transcripts, exports,
and fingerprints tied to retained content live in the ignored, access-controlled data workspace.

## Workflow

```text
discover URL -> catalog provenance -> human review -> authorized acquisition
             -> private raw storage -> ingestion -> curation -> profile build
```

Run the production audit before acquisition:

```bash
ceo-voice audit-corpus \
  --manifest configs/source-catalogs/ali-ghodsi.discovery.json \
  --policy configs/acquisition/production-policy.json \
  --output data/runtime/acquisition/ali-ghodsi-report.json \
  --pretty
```

Exit `0` means the catalog meets the configured acquisition gate. Exit `3` means the manifest is
valid but is not ready. The seed Ali Ghodsi and Matei Zaharia catalogs intentionally return `3`:
they establish verified identity anchors and access boundaries, but contain no approved post-level
voice evidence.

## Evidence roles

| Role | Intended use | Examples | Important exclusions |
|---|---|---|---|
| Primary voice | Platform-conditioned written voice | Authored X and LinkedIn posts from an authorized export/API | Reposts, likes, company copy, ghostwritten material without review |
| Supplementary voice | Cross-modal rhetorical and tonal evidence | Speaker-segmented keynote, interview, podcast, or earnings transcript | Interviewer text, captions without speaker attribution, promotional summaries |
| Factual context | Identity and topic grounding only | Official biography or event speaker page | All voice-feature analysis |

Primary and supplementary evidence remain labeled through curation. Supplementary material is
capped by policy because spoken transcripts can reveal rhetorical habits while distorting written
sentence length, punctuation, and platform formatting.

## Review requirements

An entry is eligible for voice acquisition only when all of the following hold:

- a human reviewer approved it and the manifest records that reviewer;
- authorship is supported by a first-party account, named byline, or verified speaker segment;
- acquisition does not bypass authentication or payment;
- the entry is explicitly marked eligible for voice analysis;
- a publication timestamp is available for drift and recency analysis;
- the content role is primary or supplementary voice, not factual context.

The audit additionally rejects duplicate source IDs and normalized URLs, insufficient volume,
unbalanced primary-platform coverage, and corpora dominated by supplementary evidence. X and
LinkedIn warnings are always reported because the assignment requires platform-specific behavior;
production readiness requires both through the default policy.

## Authorized import gate

Passing the corpus audit does not make an export payload trustworthy. Every connector-emitted item
must also pass `CatalogAuthorizedConnector`, a streaming decorator around the existing connector
interface. The decorator checks:

- request tenant and leader against the catalog scope;
- the export's typed `catalog_source_id` against one unique entry;
- manifest and entry review state;
- source family, platform, author, canonical URL, and publication timestamp;
- voice eligibility, authorship basis, evidence role, and access boundaries;
- SHA-256 content integrity whenever the catalog records a reviewed fingerprint.

Successful items receive an `authorization_receipt` in provider-neutral metadata. The receipt
contains no source text. It records the catalog entry, schema, acquisition method, authorship basis,
evidence role, review identity, and observed content hash. The normal ingestion pipeline preserves
this receipt through raw and clean storage, making later curation and release decisions traceable.

`LocalExportConnector` exposes `catalog_source_id` as a typed top-level export field and rejects
attempts to forge reserved governance keys inside free-form metadata. The synthetic pair at
[`data/examples/source-catalog.json`](../data/examples/source-catalog.json) and
[`data/examples/local-export.jsonl`](../data/examples/local-export.jsonl) demonstrates the matching
contract. Production adapters use the same decorator; only their transport implementation changes.

The fingerprint policy defaults to migration-compatible mode: if a reviewed fingerprint exists it
must match, while a missing fingerprint is allowed for a first authorized capture. High-assurance
imports set `require_catalog_fingerprint=true`, which rejects every entry without a pre-reviewed
hash.

## Incremental acquisition

After authorized content is captured, store its SHA-256 fingerprint and capture timestamp in the
private catalog projection. A later run compares provider identity, source version, publication
timestamp, and fingerprint before invoking ingestion. The authorization gate detects unexpected
content drift; the existing incremental planner versions expected changes and skips unchanged
content. Deletion or loss of authorization must cascade to raw text, derived observations,
evidence projections, and future release eligibility.

## Extension boundary

New network integrations implement the existing ingestion connector interface and consume approved
catalog entries. They must not embed HTTP calls, credentials, or provider-specific pagination in
the audit domain. Official APIs and account-authorized exports are preferred. Browser automation,
credential sharing, paywall avoidance, and authenticated scraping are outside the supported path.
