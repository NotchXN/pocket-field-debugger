"""Run with: python -m pocket_debugger --help."""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

from . import __version__
from .demo import demo_bytes, demo_records
from .loop import current_from_shunt, scale_current
from .modbus import RtuFramer, SerialTiming, decode_frame
from .report import render_report
from .session import analyze_record, export_csv, load_records, pair_transactions, save_records, summarize


def json_print(value):
    print(json.dumps(value, indent=2, allow_nan=False))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Standalone loop calculations and Modbus RTU capture analysis")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate a simulated session, CSV, byte fixture and HTML report")
    demo.add_argument("--output", type=Path, default=Path("demo-output"))
    decode = commands.add_parser("decode", help="Decode one complete RTU frame (including CRC)")
    decode.add_argument("hex", help="Quoted hexadecimal bytes")
    loop = commands.add_parser("loop", help="Calculate engineering units; does not control a current source")
    loop.add_argument("--current", type=float, required=True, help="Input current in mA")
    loop.add_argument("--low", type=float, default=0)
    loop.add_argument("--high", type=float, default=100)
    loop.add_argument("--unit", default="%")
    shunt = commands.add_parser("shunt", help="Convert a shunt voltage drop into loop current and engineering units")
    shunt.add_argument("--millivolts", type=float, required=True, help="Measured voltage across the shunt in mV")
    shunt.add_argument("--ohms", type=float, default=250.0, help="Shunt resistance in ohms (default 250)")
    shunt.add_argument("--low", type=float, default=0)
    shunt.add_argument("--high", type=float, default=100)
    shunt.add_argument("--unit", default="%")
    replay = commands.add_parser("replay", help="Inspect JSONL frame records and optionally export CSV")
    replay.add_argument("input", type=Path)
    replay.add_argument("--csv", type=Path)
    report = commands.add_parser("report", help="Build an offline HTML report from frame/loop JSONL")
    report.add_argument("input", type=Path)
    report.add_argument("--output", type=Path, required=True)
    frame = commands.add_parser("frame-bytes", help="Frame byte-END timestamps from device-timed JSONL")
    frame.add_argument("input", type=Path)
    frame.add_argument("--output", type=Path, required=True)
    frame.add_argument("--baud", type=int, default=9600)
    frame.add_argument("--parity", choices=("N", "E", "O"), default="E")
    frame.add_argument("--stop-bits", type=int, choices=(1, 2), default=1)
    frame.add_argument("--session-id", default="byte-capture")
    frame.add_argument("--origin", required=True, help="For example simulated or device-timestamped")
    frame.add_argument("--start", required=True, help="ISO timestamp with offset corresponding to end_us=0")
    return parser.parse_args(argv)


def frame_bytes(args):
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    if start.tzinfo is None:
        raise ValueError("--start requires a timezone offset")
    framer = RtuFramer(SerialTiming(args.baud, args.parity, args.stop_bits))
    framed = []
    with args.input.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("Each byte record must be an object")
                frame = framer.feed(item["byte"], item["end_us"])
                if frame:
                    framed.append(frame)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Byte line {number}: {error}") from error
    last = framer.finish()
    if last:
        framed.append(last)
    records = []
    for index, frame in enumerate(framed, 1):
        records.append({
            "schema_version": 1, "kind": "modbus", "session_id": args.session_id,
            "record_id": f"frame-{index:06}", "origin": args.origin,
            "observed_at": (start + timedelta(microseconds=frame["start_us"])).isoformat(),
            "serial": {"baud": args.baud, "parity": args.parity, "stop_bits": args.stop_bits},
            "timing_quality": "provided byte-end timestamps", **frame,
        })
    save_records(records, args.output)
    return {"frames": len(records), "output": str(args.output)}


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.command in ("replay", "report", "frame-bytes"):
            output = args.csv if args.command == "replay" else args.output
            if output is not None and output.resolve() == args.input.resolve():
                raise ValueError("Output must differ from input; original capture files are preserved")
        if args.command == "decode":
            result = decode_frame(bytes.fromhex(args.hex))
            json_print(result)
            return 1 if result["issues"] else 0
        if args.command == "loop":
            json_print(scale_current(args.current, args.low, args.high, args.unit))
        elif args.command == "shunt":
            current = current_from_shunt(args.millivolts, args.ohms)
            json_print({"shunt_mv": float(args.millivolts), "shunt_ohm": float(args.ohms),
                        **scale_current(current, args.low, args.high, args.unit)})
        elif args.command == "demo":
            args.output.mkdir(parents=True, exist_ok=True)
            records = demo_records()
            save_records(records, args.output / "session.jsonl")
            (args.output / "bytes.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in demo_bytes()), encoding="utf-8")
            analyzed = [analyze_record(r) for r in records]
            export_csv(analyzed, args.output / "measurements.csv")
            render_report(analyzed, args.output / "report.html")
            json_print({"origin": "simulated", **summarize(analyzed), "output": str(args.output.resolve())})
        elif args.command == "frame-bytes":
            json_print(frame_bytes(args))
        else:
            records = [analyze_record(r) for r in load_records(args.input)]
            if args.command == "report":
                json_print({"report": str(render_report(records, args.output).resolve())})
            else:
                if args.csv:
                    export_csv(records, args.csv)
                json_print({"summary": summarize(records), "transactions": pair_transactions(records),
                            "records": records})
        return 0
    except (OSError, ValueError, OverflowError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
