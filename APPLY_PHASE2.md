# Apply Phase 2 Overlay

From the existing `phase/2-compute-resilience` branch, copy this overlay into the repository root, preserving paths. Then run:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
make proto
make quality
```

The overlay intentionally contains only Phase-2 new/modified files. The full repository archive is also provided separately.

Before copying, verify:

```bash
git branch --show-current
git status
```

Expected branch: `phase/2-compute-resilience`; expected working tree: clean.
