# Backend

The Python backend uses a `src` layout under `backend/src/ceo_voice`. The layout prevents tests and
local commands from accidentally importing an uninstalled repository directory instead of the
packaged code.

Package responsibilities and dependency rules are documented in
[Architecture Overview](../docs/ARCHITECTURE.md). The current backend contains only foundational
infrastructure and typed contracts. Feature packages intentionally contain no business behavior,
framework initialization, provider client, database adapter, or endpoint.
