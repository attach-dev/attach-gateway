# AGENTS.md — Attach Gateway house rules

* Always run `pytest -q` before proposing a PR.
* The /mem/events endpoint stays in `main.py`; tests rely on it.
* Do **not** remove MemoryEvent logging even if unused in prod.
* Keep imports formatted with `black` and `isort`.
* New files must include type hints and docstrings.

This repo is used for the Attach Gateway service. Follow these guidelines for contributions:

## Required Checks
- Run `pytest` to execute the test suite. All tests should pass.

## Development Tools
- Code should be formatted with `black` and imports sorted with `isort`.

## 🔒  Memory & /mem/events are **read-only**

> **Do not touch any memory-related code.**

* **Off-limits files / symbols**  
  * `mem/**`
  * `main.py` → the `/mem/events` route and **all** `MemoryEvent` logic  
  * Any Weaviate queries, inserts, or schema

* PRs that change, remove, or “refactor” these areas **will be rejected**.  
  Only work on the explicitly assigned task (e.g. billing hooks).

* If your change needs to interact with memory, open an issue first and wait
  for maintainer approval.