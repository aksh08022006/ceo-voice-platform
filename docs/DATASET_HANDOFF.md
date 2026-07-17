# Public-content dataset handoff

The external collector should emit UTF-8 JSON Lines: one complete JSON object per physical X post or
LinkedIn post. Use the executable example in
[`data/examples/public-content-dataset.jsonl`](../data/examples/public-content-dataset.jsonl).
Validate every delivery before review:

```bash
ceo-voice validate-dataset \
  --input data/runtime/incoming/public-content.jsonl \
  --output data/runtime/incoming/validation-report.json
```

Your scraper can generate or validate against the exact runtime JSON Schema:

```bash
ceo-voice dataset-schema --output public-content.schema.json
```

Exit `0` means the file is structurally valid. It does **not** grant permission to analyze the
content. Exit `3` means the handoff is invalid. Diagnostics contain line numbers and counts but never
source text.

## Exact record contract

| Field | Required | Collector rule |
|---|---:|---|
| `schema_version` | yes | Always `1.0`. |
| `record_id` | yes | Your stable globally unique identifier. Never recycle it. |
| `leader_slug`, `leader_name` | yes | Canonical internal identity, for example `ali-ghodsi`. |
| `dataset_partition` | yes | `profile`, `held_out`, or `virality`. Held-out records must never enter profile construction. |
| `author_handle` | yes | Handle at collection time, without relying on display name alone. |
| `platform` | yes | `x` or `linkedin`. |
| `content_type` | yes | `post`, `announcement`, or `thread`. |
| `source_post_id` | yes | Native platform ID. `(platform, source_post_id)` must be unique. |
| `canonical_url` | yes | Permanent URL for the exact item. |
| `content` | yes | Exact authored text with original Unicode, line breaks, spacing, links, hashtags, and emoji. Do not clean it. |
| `content_sha256` | yes | Lowercase SHA-256 of the exact UTF-8 `content` value. |
| `language` | yes | BCP-47-style language code when known; use `und` when unknown. |
| `publication_date` | yes | ISO-8601 timestamp with timezone. Never substitute collection time. |
| `collected_at` | yes | ISO-8601 timestamp with timezone. |
| `acquisition_method` | yes | `official_api`, `authorized_export`, `public_web`, `public_transcript`, or `manual_capture`. |
| `authorship_basis` | yes | Usually `first_party_account`; do not infer authorship from writing style. |
| `reuse_permission_basis` | yes | Use `unknown` until reviewed; otherwise record the actual agreement/license/authorization. |
| `terms_url`, `license_url` | conditional | Record the exact policy or license reviewed. |
| `requires_authentication`, `requires_payment` | yes | Describe how the collector accessed the item. Never bypass either. |
| `is_repost` | yes | Reposts are retained for audit but excluded from voice evidence. |
| `is_quote_post`, `quoted_content` | yes/conditional | Keep somebody else's quoted words separate from the leader's authored text. |
| thread fields | conditional | For X threads, every physical post is a separate record with the same `thread_id`, plus `thread_position` and `thread_total`. |
| `performance` | optional | A time-pinned snapshot. Unknown metrics must be `null` or omitted, never silently converted to zero. |

`performance` accepts `reactions`, `comments`, `shares`, `saves`, `clicks`, `impressions`, and
`audience_size`, plus mandatory `collected_at` and `method`. For X, map repost/retweet count to
`shares`; for LinkedIn, map reactions to `reactions` and reposts to `shares`. Preserve the raw
platform response privately if your access agreement permits it.

## Collection rules that protect voice quality

- Collect original authored posts. Label reposts, quote posts, replies, and company-account posts;
  do not merge their text.
- Keep every line break and thread boundary. Rendered HTML, navigation labels, timestamps, and
  engagement counters must never enter `content`.
- Do not place link-preview titles, image OCR, alt text, or quoted article text inside the authored
  content field.
- Record deleted or edited versions as new snapshots using stable source identity and collection
  time. Never overwrite silently.
- Take engagement snapshots at comparable ages where possible, such as seven days after publication.
  Mixing one-hour and one-year counts without snapshot age makes virality comparisons misleading.
- Keep voice corpora and virality corpora separable. Ali/Matei authored posts can inform voice;
  cross-leader posts with measured outcomes inform structure.

## Access boundary

A publicly visible page is not automatically reusable training data. The supported collection paths
are an account-owner export, an official API under its agreement, a licensed dataset, written
permission, or item-level manual curation that passes legal/terms review. Do not automate logged-in
LinkedIn pages, evade rate limits, reuse cookies, bypass payment, or collect through undocumented
private APIs. Records with authentication, payment, repost status, or unknown reuse authority remain
blocked until a reviewer resolves them.

## Minimum useful deliveries

For each target leader, aim for at least 20 complete LinkedIn posts and 20 complete X posts for
profile construction, plus a separately flagged held-out set of at least 20 posts. For the structural
library, collect the supplied 100-profile cohort on both platforms where available, with multiple
posts per leader and comparable engagement snapshots. A list of handles alone cannot build VKR.
