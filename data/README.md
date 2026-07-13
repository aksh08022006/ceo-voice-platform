# Data Directory Policy

This directory is for local, non-production development artifacts only. Raw, interim, and processed
subdirectories are ignored by Git because executive source material and generated drafts may be
confidential, personal, licensed, or subject to retention requirements.

Rules:

- Never commit source documents, transcripts, social posts, model responses, embeddings, or
  evaluation examples containing real leader data.
- Use synthetic or explicitly licensed, de-identified fixtures under `tests/fixtures` when a later
  milestone needs committed test data.
- Preserve original source bytes separately from derived representations once ingestion exists.
- Record provenance, consent, ownership, retention, and deletion status in durable metadata—not in
  filenames.
- Production data must live in approved encrypted storage with tenant isolation and audited access.
- Embedding and derived-feature deletion must follow source deletion; derived data is not exempt
  from privacy obligations.

The ignored runtime layout is `data/raw`, `data/interim`, and `data/processed`. Those directories
should be created only by an authorized future data workflow, not by foundation setup.
