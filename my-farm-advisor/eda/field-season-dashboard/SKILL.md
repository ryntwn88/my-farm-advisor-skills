---
name: field-season-dashboard
description: Generate a single-image field-season dashboard combining Sentinel NDVI, daily weather, and CDL crop-year information for one selected field and growing season.
license: Apache-2.0
version: 1.0.0
author: my-farm-advisor
---

# Field Season Dashboard

Use this skill to produce a reusable, aligned field-season dashboard image that tells the weather-and-vegetation story for one field-year.

## When to invoke

- An advisor needs a quick seasonal read for a single field and year.
- You want NDVI, precipitation, temperature, and cumulative GDD on one shared timeline.
- You need auto-detected events (heavy rain, heat, cool periods, NDVI dips or rapid gains) annotated with short captions.

## Where to start

1. Read [GUIDE.md](GUIDE.md) for the step-by-step workflow.
2. Read [README.md](README.md) for architecture and data sources.
3. Run the script from the data-pipeline runtime with the CLI args documented in the guide.

## Routing

- Parent: `../../SKILL.md`
- EDA Index: `../INDEX.md`
