# Public research collection

The engineering task supplies 100 candidate X names and handles on pages 7–9. They are copied
exactly into `configs/source-catalogs/engineering-task-100.discovery.json`, with the PDF's SHA-256
and explicit pending identity/collection status. The role labels describe the supplied list and
are not verified current employment facts. LinkedIn URLs are unset. This is a discovery seed list,
not 100 collected profiles, an influence ranking, or a completed virality corpus.

## Capture an explicit public article

The existing `ceo-collector` commands still handle approved local social datasets. A separate
research capture command now supports anonymous public HTTPS articles:

```bash
.venv/bin/python -m ceo_voice.collector.public_web \
  --url https://blog.samaltman.com/three-observations \
  --leader-slug sam-altman \
  --leader-name 'Sam Altman' \
  --content-class post-body \
  --output data/collector/public-research/sam-altman
```

Without `--content-class`, exactly one semantic `article` container is required. HTML with missing,
ambiguous, or trivial article bodies is rejected. Plain text is supported separately. Script,
style, navigation, form, and header/footer text is excluded from the selected article body. This
simple extractor needs source-specific inspection; it is not a universal article scraper.

The command retains source bytes, exact hashes, extracted content, requested/final URLs, redirect
chain, response content type, acquisition time, robots snapshot, selector, and observed metadata.
Observed author/date values remain null when absent. Posthaven's source-provided Unix time marker
is retained verbatim as `metadata_observed["posthaven:data-unix-time"]`; an acquisition timestamp
is never substituted for a publication date. The supplied leader identity is a separate field
from observed authorship metadata.

All captures are `research_capture`, `platform: generic`, `source_modality:
authored_article_candidate`, `content_role: supplementary_voice`, and `eligible_for_generation:
false`. They do not silently enter the social handoff format, approve reuse, create a profile,
establish a person's X/LinkedIn voice, or invent engagement counts. The raw text remains under
ignored `data/collector/`; it must not be committed or bundled into the public frontend.

## Network boundaries

- Only anonymous HTTPS on port 443; no userinfo, known credential query parameters, browser
  cookies, proxy environment, authentication retries, JavaScript, or payment flows.
- Resolve each request hostname, reject private/reserved/multicast addresses and mixed DNS
  answers, and pin TCP to a validated public IP while preserving hostname TLS/SNI verification.
  Recheck every redirect destination. There is no second unconstrained DNS lookup during connect.
- Fetch and obey each origin's robots policy. HTTP 404/410 means no robots file; denial, redirection,
  unavailable robots, or a 200 HTML challenge causes an explicit failure. Robots allowances do not
  grant copyright/reuse permission. Crawl-delay and request-rate are respected within a 30-second
  interactive ceiling; larger delays stop collection.
- At most three followed redirects, 2 MB page bodies, 256 KB robots bodies, and 15-second network
  operation timeouts. Compressed responses are rejected to avoid decompression expansion.
- Output exit code 3 and a concrete reason on unsupported/blocked acquisition. There is no fallback
  to private access, alternate mirrors, fabricated records, or automatic approval.

## Demonstrated coverage, 2026-09-07

Three public articles were captured from the Sam Altman blog, using the implemented adapter and
its allowed robots policy. Each HTML document identified its site as Sam Altman and included an
observed publication Unix marker; named-author metadata was absent and remains unverified.

| Article | Exact public source | Extracted words | Source Unix publication marker |
| --- | --- | --- | --- |
| Three Observations | https://blog.samaltman.com/three-observations | 1,320 | 1739135132 |
| The Gentle Singularity | https://blog.samaltman.com/the-gentle-singularity | 1,738 | 1749589967 |
| Reflections | https://blog.samaltman.com/reflections | 1,950 | 1736127449 |

An anonymous acquisition attempt for `https://x.com/sama` stopped at `robots_disallow`; zero X
posts were collected. No LinkedIn post acquisition was attempted. Machine-readable capture and
failure summaries are stored in ignored `data/collector/public-research/collection-summary.json`
and `x-availability-check.json`.

These 5,008 article words are supplementary research evidence for a third leader, not a third
generation-ready profile. They cover a narrow topic range, have no engagement measurements, have
not passed authorship/reuse review, and have no platform-specific social holdout set. Before profile
admission, obtain direct authored X/LinkedIn records through allowed acquisition, preserve exact
publication metadata and post URLs, review source rights and authorship, and evaluate on independent
held-out posts. The recovered Ali/Matei serving bundles remain unchanged.

## Verification

`tests/unit/collector/test_public_web_capture.py` covers anonymous URL rules, private/mixed DNS
answers, pinned TLS hostname/address behavior, body limits, robots denial/challenges, redirect
limits, politeness timing, extraction/metadata, immutable repeat captures, and explicit CLI failures.
The focused suite currently contains 38 passing cases; Ruff, Black, and strict mypy pass.
