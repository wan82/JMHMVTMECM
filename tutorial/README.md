# Tutorial index

This directory is the entry point for the project tutorials. Read them in
order:

| File | Topic | Best audience |
|---|---|---|
| [00_overview.md](00_overview.md) | Project background, paper motivation, scope decisions | Everyone |
| [01_project_structure.md](01_project_structure.md) | What each directory and each file is for | Everyone |
| [02_jm_config_explained.md](02_jm_config_explained.md) | The two-layer "tuning" of JM configs, in detail | Anyone writing the paper's methodology section |
| [03_how_to_run.md](03_how_to_run.md) | Getting the pilot running from scratch | First-time hands-on users |

After reading these four files plus the top-level [README.md](../README.md)
and [HANDOFF.md](../HANDOFF.md), you should fully understand the project.

## What else lives in this directory

In addition to the four tutorials above, running `make report` auto-generates:

- `pilot_results.md` — the final results report (overwritten on every run)
- `figures/` — PNG charts (RD curves, BD-rate summary, encoding-time scaling)

These are the project's **outputs**, not tutorials. The tutorial files
(00–03) are tracked in git; the results files are typically checked in as
snapshots of a known-good baseline.

## Possible future additions

To be added as needed:

- `04_extending_to_full_ctc.md` — step-by-step guide for extending to full CTC
- `05_paper_section_drafts.md` — draft paper sections
- `06_troubleshooting.md` — collected pitfalls from real runs

If you hit something the tutorials don't cover, please loop back and add it
here for whoever comes next.
