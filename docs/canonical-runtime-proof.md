# Canonical Runtime Proof

For the current fundamentals track, BiteBuilder's canonical runtime is the top-level core:

- `bitebuilder.py` for CLI orchestration
- `parser/`, `generator/`, and `llm/` for supporting logic

`webapp.py`, `templates/`, and `static/` remain in `main` for reference, but are inactive/low-priority during the fundamentals track. The former duplicate `src/bitebuilder/` tree has been inventoried in `docs/src-bitebuilder-inventory.md` and removed from the active tree.

## Proof point

Verified locally from the repository root on 2026-04-10:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import bitebuilder
print(Path(bitebuilder.__file__).name)
print(callable(getattr(bitebuilder, "main", None)))
PY
```

Expected proof output:

```text
bitebuilder.py
True
```

Optional retained-UI check:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import webapp
print(Path(webapp.__file__).name)
PY
```

Additional supporting checks:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m compileall bitebuilder.py webapp.py parser generator llm
.venv/bin/python bitebuilder.py --help
```
