# Public data and API register

## Current truth

The repository does **not** currently contain or claim a trained real-person Ali Ghodsi or Matei
Zaharia profile. It contains synthetic showcase corpora and URL-only discovery catalogs. Raw real
content is intentionally ignored by Git because public availability does not grant redistribution,
authorship certainty, or permission to bulk scrape it.

The production pipeline is ready to ingest an operator-reviewed JSON/JSONL export, retain its raw
and clean forms, build HVM/VKR releases, and fail closed until profile authority is approved. A
model credential can now enable real provider calls, but it does not change corpus authority.

The machine-readable version of this register is
[`configs/public-data-source-register.json`](../configs/public-data-source-register.json).

## What is and is not being used

| Channel | Official access path | Assignment role | Current decision |
|---|---|---|---|
| X post history | [X API](https://docs.x.com/x-api/overview) | Primary X voice | Excluded under the assignment policy. X documents that every endpoint requires authentication, and [current pricing](https://docs.x.com/x-api/getting-started/pricing) is pay-per-use. |
| LinkedIn post history | [LinkedIn Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api) | Primary LinkedIn voice | Excluded under the assignment policy. LinkedIn uses [OAuth](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authentication), and post access is a restricted permission. Public profile rendering is not treated as permission for bulk scraping. |
| YouTube metadata/captions | [YouTube Data API](https://developers.google.com/youtube/v3/getting-started) | Supplementary spoken voice | Metadata requires API credentials; caption listing/download requires OAuth and sufficient content-owner permission. We catalog first-party Databricks event URLs but do not use undocumented caption extraction. |
| Databricks event archive | [Data + AI Summit archive](https://www.databricks.com/dataaisummit/event-archive) | Supplementary spoken voice | Used for discovery and speaker identity only. It becomes voice evidence only when a speaker-attributed transcript is lawfully supplied. |
| Matei Zaharia’s Berkeley page | [First-party homepage](https://people.eecs.berkeley.edu/~matei/) | Identity and supplementary authored material | Used for identity/publication discovery only. Multi-author academic prose is not silently attributed to one author or allowed to dominate social voice. |
| SEC EDGAR | [Public EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Earnings/filing evidence | Technically admissible because the data APIs require no key, but not applicable here: Databricks is privately held, so this does not provide the requested public-company earnings-call corpus for Ali or Matei. |
| Public podcast RSS/transcript pages | Publisher-specific RSS or transcript page | Supplementary spoken voice | Admissible only when the publisher exposes a transcript for reuse and speaker boundaries can be verified. Audio is not downloaded or transcribed merely because an episode page is public. |
| Reviewed local export | Official account export, licensed dataset, or manually curated public record | Primary/supplementary | Supported production path. `CatalogAuthorizedConnector` requires item-level provenance, authorship basis, platform, timestamp, review, and optional content hash before ingestion. |

## Why search-engine snippets are not training data

Search engines currently expose snippets from some public LinkedIn posts. Those snippets are useful
for discovering canonical post URLs, but they are incomplete, can include quoted or reshared text,
and are not an official bulk data interface. Training on them would create three silent errors:

1. another author’s embedded post could be attributed to the leader;
2. truncated text would corrupt length, closing, formatting, and CTA measurements;
3. an undocumented retrieval route would violate the task’s access constraint.

They therefore remain discovery candidates until a reviewer supplies the complete authored text
through an authorized export or item-level manual curation.

## Data needed to complete real-person calibration

For each target leader, the minimum defensible V1 corpus is:

- at least 20 complete, authored LinkedIn posts and 20 complete, authored X posts, excluding reposts;
- publication timestamp, canonical URL, platform, and authorship basis for every post;
- a held-out set of at least 20 real posts that never enters profile construction;
- speaker-attributed transcript segments as supplementary evidence, capped below written social
  evidence and excluded from punctuation/platform-format estimates;
- explicit reviewer identity and an approval record before generation permission is granted.

The manual evaluation deliverable additionally needs five X and five LinkedIn drafts per target
across the assignment’s topic types, plus human ratings. The platform can produce and score those
artifacts, but it cannot truthfully invent the missing ratings or approve its own attribution.

## Operator handoff

Supply lawful post exports as private JSON/JSONL using
[`data/examples/local-export.jsonl`](../data/examples/local-export.jsonl), add one reviewed catalog
entry per record, and run the catalog audit before importing. Raw files should remain under ignored
`data/runtime/` storage. See [Governed Corpus Acquisition](CORPUS_ACQUISITION.md) for the validation
contract and [Operations](OPERATIONS.md) for onboarding and release commands.
