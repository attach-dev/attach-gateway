# AGENTS.md – Attach Gateway house rules

* Always run `pytest -q` before proposing a PR.
* The /mem/events endpoint stays in `main.py`; tests rely on it.
* Do **not** remove MemoryEvent logging even if unused in prod.
* Keep imports formatted with `black` and `isort`.
* New files must include type hints and docstrings.