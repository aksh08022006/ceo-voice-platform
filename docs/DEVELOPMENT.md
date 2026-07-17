# Development Setup

## Supported environment

The repository standardizes on CPython 3.13. Pinning one interpreter version keeps local tooling,
the dependency lock, CI, and typing semantics aligned. A later runtime change should update
`pyproject.toml`, `requirements.lock`, CI, and this document in the same pull request.

No database, Node.js runtime, provider account, API key, or model access is needed for development,
the quality gate, or the offline integration demonstration.

## First-time setup

From the repository root:

```bash
make setup
cp .env.example .env
.venv/bin/pre-commit install
.venv/bin/pre-commit install --hook-type pre-push
make check
```

`make setup` creates `.venv`, installs the exact reviewed versions from `requirements.lock`, then
installs the local package in editable mode without resolving dependencies again.

If `make` is unavailable, run the equivalent commands:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
```

Activate the environment only if preferred; all documented commands use explicit executables so
they cannot accidentally use global packages.

## Configuration

Settings are nested under the `CEO_VOICE_` environment prefix. Double underscores separate nested
objects:

```text
CEO_VOICE_APPLICATION__SERVICE_NAME=ceo-voice-platform
CEO_VOICE_APPLICATION__ENVIRONMENT=development
CEO_VOICE_APPLICATION__DEBUG=false
CEO_VOICE_LOGGING__LEVEL=INFO
CEO_VOICE_LOGGING__FORMAT=console
```

The optional `.env` file is only for local development. Deployed environments should inject values
through their secret and configuration system. Never commit `.env`, credentials, tokens, source
documents, generated personal content, or database snapshots.

Model access is disabled by default:

```text
CEO_VOICE_MODEL__ENABLED=false
```

When a deployment enables model access, all of `PROVIDER`, `GENERATION_MODEL`, and `API_KEY` become
required. Supported provider values are `openai`, `anthropic`, and `gemini`. Model names, context
windows, output limits, retry counts, request timeouts, and optional compatible base URLs are
configuration—not constants in source code. The API constructs one pooled async transport and
closes it during application shutdown. The bundled offline demo uses deterministic fixture
providers and never reads a credential.

```text
CEO_VOICE_MODEL__ENABLED=true
CEO_VOICE_MODEL__PROVIDER=openai
CEO_VOICE_MODEL__GENERATION_MODEL=<approved-model-id>
CEO_VOICE_MODEL__API_KEY=<injected-secret>
CEO_VOICE_MODEL__CONTEXT_WINDOW_TOKENS=30000
CEO_VOICE_MODEL__MAXIMUM_OUTPUT_TOKENS=800
CEO_VOICE_MODEL__REQUEST_TIMEOUT_SECONDS=30
CEO_VOICE_MODEL__MAX_RETRIES=3
```

Do not enable model access merely to bypass profile readiness. The browser distinguishes synthetic
test fixtures, operator-transcribed development profiles, and reviewed production profiles. A
provider credential changes transport only; it does not promote corpus authority.

Environment policies:

- `development`: console logs are acceptable; debug mode may be selected deliberately.
- `test`: tests should control settings through isolated environment values.
- `staging`: deployment-like behavior without production data assumptions.
- `production`: debug mode is rejected and JSON logs are mandatory.

## Development loop

Format after editing:

```bash
make format
```

Run the complete local gate before requesting review:

```bash
make check
```

Individual checks:

```bash
make lint
make typecheck
make test
make doctor
make demo
```

Run one test module or test directly:

```bash
.venv/bin/python -m pytest tests/unit/test_settings.py
.venv/bin/python -m pytest tests/unit/test_models.py::test_document_preserves_voice_significant_whitespace
```

Pytest measures branch coverage across `ceo_voice` and fails below 95%. Coverage is a regression
signal, not permission to write assertion-free tests; tests should exercise observable invariants
and failure behavior.

## Dependency workflow

Runtime dependencies and allowed version ranges live in `pyproject.toml`. Development tools live in
the `dev` optional dependency group. The reviewed resolution lives in `requirements.lock`.

To change dependencies:

1. Change the appropriate range in `pyproject.toml`.
2. Install the resolver if the existing environment does not contain it.
3. Regenerate the lock from Python 3.13:

   ```bash
   .venv/bin/python -m piptools compile \
     --extra dev \
     --strip-extras \
     --allow-unsafe \
     --output-file requirements.lock \
     pyproject.toml
   ```

4. Recreate or synchronize a clean environment from the lock.
5. Run `make check`.
6. Review transitive upgrades and their release notes before committing the lock change.

Do not install an undeclared package and rely on local environment state. Importable production
dependencies must be declared in the main dependency list; test and quality tools belong in `dev`.

## Logging during development

Modules obtain loggers by module name:

```python
logger = get_logger(__name__)
```

Use structured `extra` fields for stable, non-sensitive identifiers. Do not interpolate secrets,
full source documents, prompt content, or generated posts into logs. An operation should be logged
at the boundary that owns it, not repeatedly at every layer.

The request context can already correlate a local unit of work. HTTP middleware and worker
adapters will establish it in future phases.

## Adding a module

Before creating a new package or abstraction, identify:

- the single owner of the behavior;
- the input and output contract;
- whether it is a domain policy, application use case, or infrastructure adapter;
- the dependency direction;
- its failure contract;
- unit, contract, and evaluation tests required for confidence.

Feature behavior should not be added to `utils`, canonical Pydantic models, package `__init__`
files, or transport adapters. Interfaces should be introduced only when there is a real caller and
at least one implementation boundary to protect.

## CI behavior

GitHub Actions uses Python 3.13 and the committed lock. It runs Ruff, Black verification, strict
mypy, and pytest. The workflow has read-only repository permissions and no secrets because this
phase requires no external services.

Local success is necessary but CI is authoritative. If a check behaves differently locally,
recreate `.venv` from the lock before changing code or weakening the check.

## Troubleshooting

### A global pytest plugin fails before tests start

Use `.venv/bin/python -m pytest`, not a globally installed `pytest`. The isolated environment
contains only declared plugins.

### Settings appear stale in a test

Settings are cached for process lifetime. Tests automatically clear the cache around each test;
custom harnesses should call `clear_settings_cache()` after changing environment variables.

### Production settings fail locally

Production requires `CEO_VOICE_LOGGING__FORMAT=json` and rejects debug mode. This is an intentional
deployment safety policy.

### A source string loses spaces

Canonical content must use `NonBlankText`, not `NonEmptyStr`. The former validates without changing
the original string. Labels and identifiers may use the trimming `NonEmptyStr` type.
