# scripts/

Runnable entrypoints and one-off utilities for the repo.

Two script shapes are acceptable here:

- Thin entrypoints that exercise code living under `jetson/`
- Standalone utilities such as data conversion, benchmark runners, and
  sanity checks

Scripts here should be:

- Small and easy to run from the command line
- Self-documenting via `--help`
- Safe to rerun without corrupting repo state

If reusable logic starts growing inside a script, move that logic under
`jetson/` and keep the script as a thin CLI wrapper.
