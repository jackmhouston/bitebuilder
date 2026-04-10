# Canonical Runtime Proof

For the current stabilization window, BiteBuilder's canonical runtime is the top-level app:

- `bitebuilder.py` for CLI orchestration
- `webapp.py` for the local Flask UI/API
- `parser/`, `generator/`, and `llm/` for supporting logic

The `src/bitebuilder/` tree remains quarantined for inventory/reference only and is not part of the packaged runtime until an explicit migration plan lands.

## Proof point

Verified locally from the repository root on 2026-04-10:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import bitebuilder, webapp
print(Path(bitebuilder.__file__).name)
print(Path(webapp.__file__).name)
print(callable(getattr(bitebuilder, "main", None)))
PY
```

Expected proof output:

```text
bitebuilder.py
webapp.py
True
```

Additional supporting checks:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m compileall bitebuilder.py webapp.py parser generator llm
.venv/bin/python bitebuilder.py --help
```
