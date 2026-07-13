# Backend

The Python backend uses a `src` layout under `backend/src/ceo_voice`. The layout prevents tests and
local commands from accidentally importing an uninstalled repository directory instead of the
packaged code.

Package responsibilities and dependency rules are documented in
[Architecture Overview](../docs/ARCHITECTURE.md). The backend now includes the source-independent
data pipeline described in [Data Pipeline](../docs/DATA_PIPELINE.md). Its connector, stage, and
repository boundaries contain real ingestion behavior without selecting a provider client,
production database, web framework, or endpoint.
