"""Portable JSONL records and decoded CSV exports, independent of any backend."""

import csv
from datetime import datetime
import json
from pathlib import Path

from .loop import scale_current
from .modbus import decode_frame


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Each record must be an object")
    if type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        raise ValueError("Unsupported or missing schema_version (expected 1)")
    stamp = record.get("observed_at")
    if not isinstance(stamp, str):
        raise ValueError("observed_at must be an ISO timestamp with timezone")
    try:
        timestamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid observed_at timestamp") from error
    if timestamp.tzinfo is None:
        raise ValueError("observed_at requires a timezone offset")
    for key in ("session_id", "record_id", "origin"):
        if not isinstance(record.get(key), str) or not record[key] or len(record[key]) > 160:
            raise ValueError(f"{key} must be nonempty text of at most 160 characters")
    kind = record.get("kind")
    if kind == "modbus":
        raw = record.get("hex")
        if not isinstance(raw, str) or len(raw) > 12288:
            raise ValueError("hex must be a bounded hexadecimal string")
        try:
            binary = bytes.fromhex(raw)
        except ValueError as error:
            raise ValueError("hex contains invalid hexadecimal bytes") from error
        if not binary or len(binary) > 4096:
            raise ValueError("Capture must contain 1 to 4096 bytes")
        notes = record.get("timing_issues", [])
        if not isinstance(notes, list) or any(not isinstance(v, str) for v in notes):
            raise ValueError("timing_issues must be a list of strings")
    elif kind == "loop":
        scale_current(record.get("current_ma"), record.get("low", 0),
                      record.get("high", 100), record.get("unit", "%"))
    else:
        raise ValueError("kind must be 'modbus' or 'loop'")
    return record


def load_records(path):
    records, seen = [], set()
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if len(line) > 65536:
                raise ValueError(f"Line {line_number}: record exceeds 64 KiB")
            if not line.strip():
                continue
            try:
                record = validate_record(json.loads(line))
                identity = (record["session_id"], record["record_id"])
                if identity in seen:
                    raise ValueError("Duplicate session_id/record_id")
                seen.add(identity)
                records.append(record)
            except (ValueError, TypeError) as error:
                raise ValueError(f"Line {line_number}: {error}") from error
    return records


def save_records(records, path):
    for record in records:
        validate_record(record)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, allow_nan=False) + "\n")


def analyze_record(record):
    validate_record(record)
    if record["kind"] == "modbus":
        decoded = decode_frame(bytes.fromhex(record["hex"]))
        timing = record.get("timing_issues", [])
        decoded["issues"].extend(timing)
        if timing:
            decoded["role"] = "unknown"
        return {**record, "decoded": decoded}
    return {**record, "scaled": scale_current(record["current_ma"], record.get("low", 0),
                                               record.get("high", 100), record.get("unit", "%"))}


def _observed(record):
    return datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))


def pair_transactions(records):
    """Conservatively pair request frames with the following response frame.

    Pairing is only attempted between frames whose direction was decoded without
    issues. A request is matched by the very next Modbus frame on the same
    session when that frame is a response from the same server address with the
    same function code (or its exception form). Any other frame closes the
    pending request as unmatched; broadcast requests never expect a response.
    Turnaround is derived from record timestamps, whose precision depends on the
    capture's timing provenance.
    """
    transactions, pending = [], {}

    def close(session, outcome):
        request = pending.pop(session, None)
        if request is not None:
            transactions.append({"session_id": session, "request_id": request["record_id"],
                                 "response_id": None, "address": request["decoded"]["address"],
                                 "function": request["decoded"]["function"], "outcome": outcome,
                                 "exception": False, "turnaround_ms": None})

    for record in records:
        if record["kind"] != "modbus":
            continue
        session, decoded = record["session_id"], record["decoded"]
        role = decoded["role"] if not decoded["issues"] else "unknown"
        request = pending.get(session)
        if request is not None and role == "response":
            expected = request["decoded"]
            if decoded["address"] == expected["address"] and decoded["function"] & 0x7F == expected["function"]:
                turnaround = (_observed(record) - _observed(request)).total_seconds() * 1000.0
                transactions.append({
                    "session_id": session, "request_id": request["record_id"],
                    "response_id": record["record_id"], "address": decoded["address"],
                    "function": expected["function"], "outcome": "paired",
                    "exception": bool(decoded["function"] & 0x80),
                    "turnaround_ms": round(turnaround, 3) if turnaround >= 0 else None,
                })
                del pending[session]
                continue
        if request is not None:
            close(session, "unmatched")
        if role == "request":
            if decoded["address"] == 0:
                transactions.append({"session_id": session, "request_id": record["record_id"],
                                     "response_id": None, "address": 0, "function": decoded["function"],
                                     "outcome": "broadcast", "exception": False, "turnaround_ms": None})
            else:
                pending[session] = record
    for session in list(pending):
        close(session, "unmatched")
    return transactions


def summarize(records):
    frames = [r["decoded"] for r in records if r["kind"] == "modbus"]
    transactions = pair_transactions(records)
    return {
        "records": len(records), "modbus_frames": len(frames),
        "crc_errors": sum(f["crc_valid"] is False for f in frames),
        "frames_with_issues": sum(bool(f["issues"]) for f in frames),
        "exception_responses": sum(f["role"] == "response" and
                                   any("exception_code" in c for c in f["candidates"]) for f in frames),
        "ambiguous_frames": sum(f["role"] == "ambiguous" for f in frames),
        "loop_readings": sum(r["kind"] == "loop" for r in records),
        "transactions_paired": sum(t["outcome"] == "paired" for t in transactions),
        "unmatched_requests": sum(t["outcome"] == "unmatched" for t in transactions),
        "broadcast_requests": sum(t["outcome"] == "broadcast" for t in transactions),
    }


def csv_text(value):
    text = str(value)
    # Capture labels may be untrusted; prevent spreadsheet formula interpretation.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def export_csv(records, path):
    fields = ["session_id", "record_id", "observed_at", "origin", "kind", "address",
              "function", "role", "crc_valid", "hex", "current_ma", "percent",
              "engineering_value", "unit", "range_status", "namur_status", "issues"]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in fields[:5]}
            if record["kind"] == "modbus":
                decoded = record["decoded"]
                row.update({key: decoded[key] for key in ("address", "function", "role", "crc_valid", "hex")})
                row["issues"] = "; ".join(decoded["issues"])
            else:
                row.update({key: record["scaled"][key] for key in
                            ("current_ma", "percent", "engineering_value", "unit", "range_status", "namur_status")})
            writer.writerow({k: csv_text(v) if isinstance(v, str) else v for k, v in row.items()})
