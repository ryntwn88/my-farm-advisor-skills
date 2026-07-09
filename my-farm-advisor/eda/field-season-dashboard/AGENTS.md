# Local Instructions

## Purpose

This folder owns the reusable field-season dashboard workflow that combines Sentinel NDVI, daily weather, and CDL crop-year data into a single aligned PNG for one field and one growing season.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes. When testing the dashboard script, run it against the default test case (ia-grower, ia-grower-iowa, osm-1360326425, 2025) to verify the PNG is produced and panels render correctly.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
