# Pocket Field Debugger

**Handheld Loop Calibrator & Modbus RTU Sniffer**

A standalone maintenance tool project for investigating 4-20 mA instrument loops and Modbus RTU links. The first release provides a working software foundation and an offline demo before purchasing or building hardware.

**Version 0.1.0: software prototype.** The decoder, capture replay, engineering calculations, and report work today. Live acquisition, STM32 firmware, electrical measurement, current sourcing, PCB layout, and calibration validation are future milestones. The calculator does not set an electrical output. No backend, account, cloud service, or hardware is required to run the demo.

## Quick start

Install Python 3.11 or newer, open a terminal in this repository, and run:

```console
python -m pocket_debugger demo --output demo-output
```

Open `demo-output/report.html` in your normal browser. Alternatively, open the included `examples/demo/report.html` immediately. Reports are self-contained and make no network requests. The demo is labeled **SIMULATED SESSION** throughout its records and report.

The demo generates:

| File | Contents |
| --- | --- |
| `session.jsonl` | Eight Modbus frames and six loop readings, including deliberately problematic records |
| `measurements.csv` | Decoded frame fields, scaled loop values and NAMUR NE 43 status |
| `report.html` | Searchable capture log, record inspector, current plot, transaction table, and interactive scaling calculator |
| `bytes.jsonl` | Two frames represented as simulated byte-END timestamps |

Expected summary: **14 records, 8 RTU frames, 1 CRC error, 1 exception response, 2 ambiguous frames, 6 loop readings, 2 paired transactions, and 1 unmatched request**.

## Commands

Decode a complete RTU frame with its CRC:

```console
python -m pocket_debugger decode "01 03 00 00 00 0A C5 CD"
```

Scale a current reading into engineering units:

```console
python -m pocket_debugger loop --current 12 --low 0 --high 10 --unit bar
```

This returns 50% of span and 5 bar. Out-of-range values are retained without clamping; 21 mA becomes 106.25% of span. `range_status` describes the configured 4-20 mA span. `namur_status` classifies the current against the nominal NAMUR NE 43 levels: `failure_low` below 3.6 mA, `saturated_low` from 3.6 mA, `measuring` from 3.8 to 20.5 mA, `saturated_high` to 21.0 mA, and `failure_high` above it. A transmitter may be configured with different failure currents; check its documentation before acting on the flag.

Convert a shunt voltage drop into loop current and engineering units:

```console
python -m pocket_debugger shunt --millivolts 3000 --ohms 250 --low 0 --high 10 --unit bar
```

This is a calculation only; the software does not read a voltmeter.

Replay a saved session, pair transactions, and export CSV:

```console
python -m pocket_debugger replay examples/demo/session.jsonl --csv demo-output/replay.csv
python -m pocket_debugger report examples/demo/session.jsonl --output demo-output/review.html
```

Frame a capture with device-provided timestamps:

```console
python -m pocket_debugger frame-bytes examples/demo/bytes.jsonl --output demo-output/framed.jsonl --origin simulated --start "2026-10-03T09:00:00+07:00" --baud 9600 --parity E --stop-bits 1
```

Use `--origin device-timestamped` only for real acquisition data with that provenance. Timestamps specify the END of each byte, not the moment a laptop receives a USB buffer. Without parity, use `--parity N --stop-bits 2`. See [capture format](docs/capture-format.md).

Exit codes: `0` for a completed command, `1` when `decode` finds frame issues, and `2` for invalid input or file errors. Replay succeeds even when it contains deliberately retained bad frames; inspect its summary and records.

`replay` and the report also list **transactions**. A request is paired only with the very next Modbus frame of the same session when that frame is a cleanly decoded response from the same server address with the same function code or its exception form. Any other frame leaves the request `unmatched`; broadcast requests are recorded as `broadcast` and never wait for a reply. Turnaround time is taken from record timestamps, so its precision follows the capture's timing provenance. Pairing never changes a frame's decoded role: ambiguous write echoes stay ambiguous and are not paired.

For an optional installed command, run `python -m pip install .` and use `pocket-debugger`. Direct `python -m pocket_debugger` operation requires no third-party packages or installation step.

## Decoder coverage

- Modbus CRC-16 with low-byte-first wire order.
- Functions 01, 02, 03, 04, 05, 06, 15, and 16, plus exception responses.
- Quantity, payload length, byte-count, serial address, and address-range checks.
- Raw bytes retained for corrupt, short, oversized, and unsupported frames.
- Conservative direction inference: identical write echoes and overlapping read-coil shapes remain ambiguous.
- Byte framing at t1.5/t3.5, including the recommended fixed timing above 19200 baud.

This version does not infer timeouts, decode register-map units, scan addresses, transmit Modbus requests, or infer baud rate. Transaction pairing is conservative and sequential; it does not reorder frames or recover from interleaved masters. CRC correctness is distinct from timing correctness. Framing from a capture that begins mid-frame or ends without verified silence has corresponding limits described in the format guide.

## Development and verification

```console
python -m unittest discover -s tests -v
```

The 57 tests cover reference CRC bytes, decoding and malformed frames, timing boundaries, engineering scaling, NAMUR levels, transaction pairing, session validation, export handling, source-file preservation, and complete demo/replay/report workflows. Tests create and clean bounded scratch directories under `.test-work/` in the checkout.

With Node.js available, an optional smoke test checks the generated report's JavaScript syntax, embedded demo data, filters, inspector, calculator and export wiring with a small DOM substitute (not a browser rendering test):

```console
node tests/report-smoke.cjs demo-output/report.html
```

GitHub Actions runs the test suite, the demo, replay/report/frame-bytes commands, the report smoke test, and a packaging check on Windows/Linux with Python 3.11-3.13. See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Project layout

```text
pocket_debugger/       Decoder, timing framer, loop math, sessions, CLI, report
tests/                 Software verification
examples/demo/         Ready-to-open simulated capture and report
docs/                  Architecture, file format, bench checks, roadmap
hardware/              Design requirements and tentative BOM categories
.github/workflows/     Software CI
```

The [hardware plan](hardware/README.md) defines the future receive-only interface and loop-measure/source paths. The [roadmap](docs/roadmap.md) describes the next build milestones. The [validation record](docs/validation.md) distinguishes checks performed here from hardware and CI work still outstanding.

## References and license

Protocol behavior is based on the [Modbus Serial Line Guide V1.02](https://www.modbus.org/file/secure/modbusoverserial.pdf) and [Modbus Application Protocol V1.1b3](https://www.modbus.org/file/secure/modbusprotocolspecification.pdf). See [bench verification](docs/bench-verification.md) for the hardware tests required before adopting measured performance claims.

Original software and documentation are provided under the [MIT license](LICENSE). No third-party firmware, circuit design, or hardware certification is included.
