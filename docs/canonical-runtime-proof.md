# Canonical Runtime Proof

For the current BiteBuilder workspace track, the canonical runtime is the top-level Python core plus the local browser workspace:

- `webapp.py` for the active browser workspace at `/workspace`
- `bitebuilder.py` for CLI orchestration and deterministic export flows
- `parser/`, `generator/`, and `llm/` for supporting logic

`templates/` and `static/` are active parts of the product surface. The former duplicate `src/bitebuilder/` tree has been inventoried in `docs/src-bitebuilder-inventory.md` and removed from the active tree. The Go TUI under `go-tui/` remains in the repo, but it is currently on hold while UI/UX work is focused on the webapp.

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

Workspace proof:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import webapp
print(Path(webapp.__file__).name)
print(hasattr(webapp, "app"))
PY
```

Expected workspace proof output:

```text
webapp.py
True
```

Additional supporting checks:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m compileall bitebuilder.py webapp.py parser generator llm
.venv/bin/python bitebuilder.py --help
./bin/bitebuilder flask-smoke
```
