"""Deterministic fixtures, explicitly labeled simulated."""

from datetime import datetime, timedelta, timezone

from .modbus import SerialTiming, with_crc


def demo_records():
    start = datetime(2026, 10, 3, 9, 0, tzinfo=timezone(timedelta(hours=7)))
    frames = [
        (0, with_crc(bytes.fromhex("01 03 00 00 00 02"))),
        (20, with_crc(bytes.fromhex("01 03 04 00 64 00 C8"))),
        (100, with_crc(bytes.fromhex("01 04 00 00 00 01"))),
        (122, with_crc(bytes.fromhex("01 84 02"))),
        (200, with_crc(bytes.fromhex("01 06 00 10 00 01"))),
        (220, with_crc(bytes.fromhex("01 06 00 10 00 01"))),
        (300, with_crc(bytes.fromhex("02 03 00 00 00 01"))),
        (323, bytes.fromhex("02 03 02 00 FA 00 00")),
    ]
    readings = [(400, 4.0), (500, 8.0), (600, 12.0), (700, 16.0), (800, 20.0), (900, 21.0)]
    records = []
    for index, (milliseconds, raw) in enumerate(frames, 1):
        records.append({
            "schema_version": 1, "session_id": "bench-demo-001", "record_id": f"frame-{index:03}",
            "observed_at": (start + timedelta(milliseconds=milliseconds)).isoformat(),
            "origin": "simulated", "kind": "modbus", "hex": raw.hex(" ").upper(),
            "timing_quality": "frame fixture; wire timing not measured",
        })
    for index, (milliseconds, current) in enumerate(readings, 1):
        records.append({
            "schema_version": 1, "session_id": "bench-demo-001", "record_id": f"loop-{index:03}",
            "observed_at": (start + timedelta(milliseconds=milliseconds)).isoformat(),
            "origin": "simulated", "kind": "loop", "current_ma": current,
            "low": 0.0, "high": 10.0, "unit": "bar",
        })
    return records


def demo_bytes():
    """Byte-END timestamps at 9600 8E1; this contains two valid frames."""
    timing = SerialTiming()
    end_us = timing.character_us
    records = []
    for raw in (with_crc(bytes.fromhex("01 03 00 00 00 02")),
                with_crc(bytes.fromhex("01 03 04 00 64 00 C8"))):
        for byte in raw:
            records.append({"end_us": round(end_us, 6), "byte": byte})
            end_us += timing.character_us
        end_us += 5000.0
    return records
