# Repository Guidelines

This repo is used for the Attach Gateway service. Follow these guidelines for contributions:

## Required Checks
- Run `pytest` to execute the test suite. All tests should pass.

## Development Tools
- Code should be formatted with `black` and imports sorted with `isort`.

## Known Issues and TODOs
- Rename the session header in `middleware/session.py` from `X-UMP-Session-Id` to `X-Attach-Session`.
- Update all references to the old header name.
- Correct the quick-start instructions in `README.md` to use `python script/start_weaviate.py` instead of `scripts/`.
- Fix the error message in `auth/oidc.py` that references `.cursorrules`; it should point to the README for environment setup.
- Add tests for the session middleware (`session_mw`) covering missing `sub` handling and header injection. Place them in `tests/test_session_middleware.py`.
