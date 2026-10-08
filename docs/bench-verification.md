# Bench verification plan

These are future physical checks, not completed results.

## Modbus acquisition

1. Use a known client/server pair and an independent logic analyzer or reference capture.
2. Confirm that the sniffer's transmitter remains disabled, including reset and watchdog states.
3. Compare captured bytes and timestamps against the reference at configured baud/parity settings.
4. Inject CRC corruption, exceptions, long internal gaps, partial frames, and sustained traffic.
5. Measure buffering limits and confirm overflow is recorded instead of silently dropping data.
6. Compare link behavior before and after attaching the tool. Record bus loading and any observed errors.

Acceptance evidence: reference traces, capture configuration, firmware version, timing comparison, overflow tests, and documented leading/trailing capture limits. Laptop serial arrival timestamps alone do not satisfy timing validation.

## Loop measurement and source

1. Build an explicit low-voltage bench loop with a current-limited supply and a calibrated reference meter.
2. Compare measurement and source output at 4, 8, 12, 16, and 20 mA. Repeat sweeps in both directions.
3. Record shunt burden, supply voltage, load, warm-up time, temperature, repeatability, and reference uncertainty.
4. Test output-disabled startup, hardware mode change, open load, reversed connection, compliance limit, and fault shutdown within the designed protection envelope.
5. Calculate gain/offset, nonlinearity, and uncertainty. Independently verify any calibration correction using points not used to fit it.

Acceptance evidence: raw readings and error table under specified conditions, measured compliance/load range, protection results, and calibration provenance. DAC/ADC bit depth is not a demonstrated accuracy specification.

## File and report workflow

Capture a real session, export it, replay it on another computer, and compare raw bytes, metadata, numeric values, and flags. Verify device-timed acquisition is distinguished from manual or simulated data. Inspect the report in the target browser and at the intended screen size before treating its layout as visually verified.
