# scripts/

One-off utilities: data capture wrappers, format conversion, benchmark
runners, sanity checks.

Scripts here should be:

- Single-file Python (no package layout, no imports from `jetson/`)
- Self-documenting via `--help`
- Idempotent (rerunning does not corrupt state)

If a script grows into something the pipeline depends on, move it under
`jetson/` and import it properly.
