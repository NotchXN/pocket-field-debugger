# Validation record

Build date: 3 October 2026.

## Completed

- Local automated suite: 48 tests passed on bundled Python 3.12.14 on Windows.
- Demo generation: 14 records with the documented intentional CRC failure, exception, ambiguous frames, and loop-range overflow.
- End-to-end replay, CSV export, HTML generation, and byte-timestamp framing exercised by tests.
- JSONL round trips, malformed input, duplicate IDs, timezone requirements, non-finite measurements, CSV formula handling, script-tag escaping, and prevention of output overwriting source captures checked.
- Generated report JavaScript syntax and embedded session JSON checked with Node.js.

The environment's temporary-directory permissions prevented the first file tests from running. Test scratch creation was changed to a bounded local directory with inherited permissions, after which the full suite passed. No application behavior was disabled to obtain passing results.

## Not yet verified

- Actual wire acquisition, analog measurement, current sourcing, firmware, and PCB hardware.
- Electrical accuracy, calibration uncertainty, isolation, protection, and compliance voltage.
- Remote GitHub Actions matrix; the repository has not been published.
- Report visual layout and browser interactions. The app's browser URL policy rejected a local `file:` preview. The delivered report remains a normal HTML file that can be opened manually in a browser.

The report's embedded JavaScript is also syntax-checked during local packaging. This is not a substitute for visual/browser verification.

## Revision 0.1.1 (8 October 2026)

- Full suite re-run on Linux with Python 3.13: 57 tests passed.
- New tests cover the write-single length fix, NAMUR NE 43 levels and sequential transaction pairing (paired, exception, unmatched, ambiguous, broadcast, cross-session).
- Report JavaScript executed against the regenerated demo output with the Node.js DOM-substitute smoke test (`tests/report-smoke.cjs`); still not a browser rendering test.
- Packaging verified with `python -m pip install .` followed by the console script `--version`.
- `examples/demo/` regenerated from the 0.1.1 code so bundled artifacts match the current output format.
- The remote GitHub Actions matrix has still not been run; the workflow now also performs the steps above.
