# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-10-08

### Added

- Conservative sequential transaction pairing (`pair_transactions`) with turnaround
  time, exposed in `replay` output, the session summary and a new report table.
- `namur_status` field in loop calculations and CSV exports classifying the current
  against the nominal NAMUR NE 43 levels; the report calculator shows it live.
- `shunt` command converting a shunt voltage drop into loop current and engineering units.
- `tests/report-smoke.cjs` Node.js smoke test for the generated report, run in CI.
- CI now also exercises `report`, `frame-bytes`, a packaging install and the console script,
  and uploads the demo output as a workflow artifact.

### Fixed

- Write-single frames (functions 05/06) with an invalid length were reported as an
  unsupported function in addition to the length issue; only the length issue remains.

### Changed

- `pyproject.toml` uses the SPDX `license` expression and declares classifiers.

## [0.1.0] - 2026-10-03

- Initial standalone software prototype: RTU decoder, byte framer, loop
  calculations, JSONL sessions, CSV export, offline HTML report, tests and CI.
