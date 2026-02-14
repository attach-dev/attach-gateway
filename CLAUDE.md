# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Attach Gateway is a Python-based **OIDC/DID identity sidecar** for LLM engines (Ollama, vLLM) and multi-agent frameworks. It provides OIDC/DID-JWT authentication as the core, with optional A2A handoff, pluggable memory backends, and usage/quota features that can be enabled when needed.

## Design / Code Philosophy

**Attach is an identity sidecar first.** Many users install and run Attach only to enforce OIDC/DID auth and stamp identity/session headers in front of an LLM engine. That "OIDC sidecar" path must remain:
- fast to start
- low overhead
- stable and backwards compatible

**Opt-in, not mandatory.** Any feature beyond OIDC/DID auth (memory backends, A2A routing, quotas, metering, MCP gateway, etc.) must be:
- gated behind explicit flags/config (env vars, config files, or CLI subcommands)
- disabled by default
- "lazy-loaded" (avoid importing heavy modules or starting background tasks unless the feature is enabled)

**No surprise dependencies.**
- Keep the base install lean.
- Add heavyweight or optional integrations as extras (e.g. `.[quota]`, `.[usage]`, `.[full]`) and ensure the default path does not require them.
- Missing optional env vars must not crash the gateway; prefer graceful fallbacks with clear warnings.

**Local-first and privacy-respecting by default.**
- No phone-home behavior unless explicitly enabled.
- Default logs/metrics should be local-only. If remote metering is supported, it must be opt-in and non-fatal.

**Safe-by-default changes.**
- New routes/middlewares must not weaken authentication requirements for existing endpoints.
- Avoid breaking changes to required environment variables or the default startup flow.

## Build and Development Commands

```bash
# Install from source with all dev dependencies
pip install -e ".[dev,full]"

# Run the gateway (development)
uvicorn main:app --port 8080 --reload

# Run the gateway (CLI)
attach-gateway --port 8080

# Format code
black .
isort .

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_jwt_middleware.py -v

# Run tests with coverage
pytest tests/ --cov=.
```

## Required Environment Variables

```bash
OIDC_ISSUER=https://your-domain.auth0.com/  # OIDC provider issuer URL
OIDC_AUD=your-api-identifier                 # Expected JWT audience claim
```

Optional variables:
- `ENGINE_URL`: LLM engine endpoint (default: `http://localhost:11434`)
- `MEM_BACKEND`: Memory backend - `none` (default), `weaviate`, or `sakana`
- `WEAVIATE_URL`: Required if `MEM_BACKEND=weaviate`
- `MAX_TOKENS_PER_MIN`: Enables token quota middleware
- `USAGE_METERING`: `null` (default), `prometheus`, or `openmeter`
  - Note: metering backends must remain optional; missing keys/config should gracefully fall back to `null` behavior.

## Architecture

### Request Flow
```
Client Request → middleware/auth.py (JWT validation)
              → middleware/session.py (session ID generation)
              → proxy/engine.py or a2a/routes.py
              → Memory backend (fire-and-forget write)
```

### Key Modules
- **auth/**: OIDC JWT and DID token verification (`oidc.py`, `did.py`)
- **middleware/**: Stateless header processing - auth extraction, session stamping, quota enforcement
- **proxy/**: Engine-agnostic HTTP streaming proxy to Ollama/vLLM
- **a2a/**: Agent-to-agent task routing (`/a2a/tasks/send`, `/a2a/tasks/status`)
- **mem/**: Pluggable memory backends with factory pattern
- **usage/**: Token metering backends (Prometheus, OpenMeter)

### Authentication Dispatch
`auth/__init__.py` routes tokens by format:
- 2 dots → OIDC JWT (`auth/oidc.py`) - RS256/ES256 only
- 3+ dots → DID token (`auth/did.py`) - did:key or did:pkh

## Code Conventions

- Python 3.10+ with type hints everywhere using `from __future__ import annotations`
- All FastAPI routes must be `async`; wrap blocking I/O in `loop.run_in_executor`
- Use `aiter_bytes()` for streaming responses (constant memory)
- Module size limit: 400 lines; extract helpers if larger
- Format with `black`, sort imports with `isort`
- Commit messages: Conventional Commits (`feat:`, `fix:`, `docs:`)

## Security Requirements

- Reject HS256 JWTs; only accept RS256/ES256
- Enforce `aud` and `exp` claims (60s clock skew allowed)
- Session IDs: `sha256(user.sub + user-agent)` - non-guessable
- Log only first 8 chars of JWT `sub` claim; never log full tokens

## Testing

- Use `pytest-asyncio` for async tests
- Mock network calls with `httpx.MockTransport`
- Test files in `tests/` directory
- Config: `pytest.ini` sets `pythonpath = .`

## Starting Local Services

```bash
# Start Weaviate memory backend
docker run --rm -d -p 6666:8080 \
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  semitechnologies/weaviate:1.30.5

# Or use the helper script
python script/start_weaviate.py
```

## Multi-Agent Demo

```bash
# Terminal 1: Gateway
uvicorn main:app --port 8080

# Terminal 2: Planner agent
uvicorn examples.agents.planner:app --port 8100

# Terminal 3: Coder agent
uvicorn examples.agents.coder:app --port 8101

# Terminal 4: Demo UI
cd examples/static && python -m http.server 9000
# Open http://localhost:9000/demo.html
```
