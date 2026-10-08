# Roadmap

## v0.1 - Offline software foundation (implemented)

- Conservative RTU decoding and CRC validation.
- Device-timestamped byte framing and portable capture records.
- Loop engineering calculations and CSV export.
- Deterministic demo and self-contained interactive report.
- Software tests, CI configuration, and hardware development requirements.
- Conservative sequential request/response pairing with turnaround time (v0.1.1).
- NAMUR NE 43 signal-level classification and shunt-voltage conversion command (v0.1.1).

## v0.2 - Receive-only bench acquisition

Select an MCU development board and isolated interface. Build firmware that timestamps UART data, emits the documented capture format, and reports overflow. Add a host transport adapter only after the device protocol is established. Validate bus timing and receive-only behavior against an independent reference.

Create milestone issues:

1. Select board and publish pin/power-domain diagram.
2. Build isolated receive-only bench interface.
3. Implement UART timestamping and bounded ring buffer.
4. Implement USB session transport and overflow records.
5. Extend transaction correlation with timeout inference and partial-capture handling (sequential pairing exists since v0.1.1).
6. Publish benchmark traces and supported serial settings.

## v0.3 - Loop measurement

Evaluate ADC/reference/shunt choices, design protection, measure burden and errors, and add provenance-aware raw ADC records. Compare against a calibrated meter. Define accuracy targets from those results.

## v0.4 - Controlled current source

Design the powered source circuit and hardware output enable. Implement and validate the fail-safe mode state machine, compliance behavior, preset setpoints, and an output-disabled startup. Add measured output feedback before a ramp feature.

## v1.0 - Validated handheld prototype

Publish KiCad sources, a validated BOM, firmware build instructions, enclosure CAD, electrical limits, calibration procedure, and reproducible bench evidence. Refine the handheld UI and power design. Keep transmitter simulation, HART support, and automatic baud detection as later independently scoped features.

Milestone completion requires its evidence, not only code compilation or a rendered design. No delivery dates or hardware certification claims are assigned before board and circuit evaluation.
