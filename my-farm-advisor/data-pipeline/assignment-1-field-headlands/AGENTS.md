# Local Instructions

## Purpose

This folder owns the Assignment 1 field headlands buffer subskill. It reads **individual field boundary GeoJSON files** from the data-pipeline runtime, computes a 21 m headlands buffer ring in **per-field UTM**, and writes three outputs per field (`field_boundary.gpkg`, `headlands_ring.gpkg`, and `headlands_validation.png`) under the field's own `derived/headlands/` directory.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling data-pipeline workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. For data-pipeline runtime conventions, read `../AGENTS.md` and `../README.md`. If routing context is needed, read `../../INDEX.md` and `../../../SKILL.md`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes. After code changes, test against the runtime:

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd /home/coder/my-farm-advisor-skills/my-farm-advisor/data-pipeline/assignment-1-field-headlands
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_assignment_1_headlands.py
```

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../AGENTS.md`.
