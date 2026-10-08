# Capture format v1

One JSON object per UTF-8 line. A UTF-8 BOM and blank lines are accepted. Every session record requires integer `schema_version: 1`, nonempty `session_id`, `record_id`, and `origin`, a timezone-aware ISO `observed_at`, and `kind`.

Duplicate `(session_id, record_id)` pairs in an input file are rejected. The file must preserve capture order where that order matters; replay does not sort observations or invent transactions.

## Complete-frame record

```json
{"schema_version":1,"session_id":"bench-001","record_id":"frame-001","observed_at":"2026-10-03T09:00:00+07:00","origin":"device-timestamped","kind":"modbus","hex":"01 03 00 00 00 0A C5 CD"}
```

`hex` contains the complete RTU ADU, including its two CRC bytes. A capture record can retain 1-4096 raw bytes, including invalid data. Valid RTU frames have at most 256 bytes; the decoder flags oversized records. No physical bus direction is asserted by the record.

Optional metadata includes `timing_quality`, `serial`, `timing_issues`, device IDs, notes, and acquisition flags. A nonempty `timing_issues` list prevents assigning a reliable inferred direction even when the CRC is valid. Unknown metadata is retained but not automatically interpreted; schema v1 is deliberately extensible.

## Loop record

```json
{"schema_version":1,"session_id":"bench-001","record_id":"loop-001","observed_at":"2026-10-03T09:00:00+07:00","origin":"manual-reference","kind":"loop","current_ma":12.0,"low":0.0,"high":10.0,"unit":"bar"}
```

Current and engineering range endpoints must be finite numbers. The upper range must exceed the lower range. Defaults are `low=0`, `high=100`, and `unit="%"`. Booleans, NaN, and infinities are not measurements.

Calculation: `fraction = (current_ma - 4) / 16`; `value = low + fraction * (high - low)`. Reverse-acting ranges are not supported in v0.1. Values outside the current span remain numeric and receive a range flag. These flags do not diagnose an instrument's fault signaling.

## Byte timestamp input

The `frame-bytes` command uses a separate acquisition-stream format:

```json
{"end_us":1145.833333,"byte":1}
{"end_us":2291.666667,"byte":3}
```

`byte` is an integer 0-255. `end_us` is the finite, nonnegative microsecond timestamp at the END of the byte on the wire. Timestamps cannot overlap or run backwards. Rounded timestamps are accepted within a 0.01 microsecond comparison tolerance.

For adjacent bytes, silence is `next_end - previous_end - character_duration`. Counting byte duration as silence would falsely split valid traffic. At baud rates through 19200, thresholds are derived from character duration; above 19200 the implementation uses the guide's recommended 750 us and 1750 us thresholds. Even/odd parity defaults to one stop bit. No parity requires two stop bits.

`--start` is the timezone-aware date/time corresponding to timer value zero. `observed_at` is derived from the first byte's start. For a first timestamp shorter than one character, the calculated start is bounded at zero because acquisition may have begun partway through that byte.

A long internal gap is retained as a timing issue. A gap at least t3.5 ends the preceding frame and sets `trailing_silence_verified=true`. At end of input, `finish()` emits the remaining bytes with `trailing_silence_verified=false`; it does not pretend trailing bus silence was observed. Leading silence at the beginning of a capture is also unverified.

Future real captures must add receiver overflow and acquisition-boundary metadata. Data from a generic USB-UART read timestamp is insufficient for claiming protocol timing compliance. The included byte example is simulated and contains two complete frame fixtures.
