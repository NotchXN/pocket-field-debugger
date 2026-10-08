import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import unittest
import uuid

from pocket_debugger.__main__ import main
from pocket_debugger.demo import demo_records
from pocket_debugger.loop import current_from_shunt, namur_status, scale_current
from pocket_debugger.report import render_report
from pocket_debugger.session import analyze_record, export_csv, load_records, pair_transactions, save_records, summarize, validate_record


@contextlib.contextmanager
def temporary_directory():
    # Normal inherited Windows permissions; fixture files stay inside this checkout.
    root = (Path.cwd() / ".test-work").resolve()
    root.mkdir(exist_ok=True)
    directory = root / uuid.uuid4().hex
    directory.mkdir()
    try:
        yield str(directory)
    finally:
        if directory.resolve().parent != root or directory.is_symlink():
            raise RuntimeError("Test cleanup target escaped its scratch directory")
        shutil.rmtree(directory)


class LoopTests(unittest.TestCase):
    def test_endpoints_and_midpoint(self):
        for current, expected in ((4, 0), (12, 5), (20, 10)):
            self.assertEqual(scale_current(current, 0, 10, "bar")["engineering_value"], expected)

    def test_out_of_range_is_not_clamped(self):
        self.assertEqual(scale_current(21)["percent"], 106.25)
        self.assertEqual(scale_current(3.5)["range_status"], "below_range")

    def test_shunt_conversion(self):
        self.assertEqual(current_from_shunt(300, 25), 12)

    def test_namur_ne43_levels(self):
        expected = {3.0: "failure_low", 3.6: "saturated_low", 3.79: "saturated_low", 3.8: "measuring",
                    12.0: "measuring", 20.5: "measuring", 20.6: "saturated_high", 21.0: "saturated_high",
                    21.01: "failure_high"}
        for current, status in expected.items():
            self.assertEqual(namur_status(current), status, current)
            self.assertEqual(scale_current(current)["namur_status"], status)
        with self.assertRaises(ValueError):
            namur_status(float("nan"))

    def test_invalid_numbers(self):
        for current in (None, True, "12", float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                scale_current(current)
        with self.assertRaises(ValueError):
            scale_current(12, 10, 10)
        with self.assertRaises(ValueError):
            current_from_shunt(300, 0)

    def test_derived_overflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "Derived scaling"):
            scale_current(1e308, 0, 1e308)


class SessionTests(unittest.TestCase):
    def test_roundtrip_and_demo_summary(self):
        with temporary_directory() as directory:
            path = Path(directory) / "session.jsonl"
            records = demo_records()
            save_records(records, path)
            self.assertEqual(load_records(path), records)
            summary = summarize([analyze_record(r) for r in records])
            self.assertEqual(summary, {"records": 14, "modbus_frames": 8, "crc_errors": 1,
                                      "frames_with_issues": 1, "exception_responses": 1,
                                      "ambiguous_frames": 2, "loop_readings": 6,
                                      "transactions_paired": 2, "unmatched_requests": 1,
                                      "broadcast_requests": 0})

    def test_duplicate_identity_rejected(self):
        with temporary_directory() as directory:
            path = Path(directory) / "session.jsonl"
            record = demo_records()[0]
            save_records([record, record], path)
            with self.assertRaisesRegex(ValueError, "Line 2.*Duplicate"):
                load_records(path)

    def test_naive_time_and_wrong_schema_rejected(self):
        record = demo_records()[0]
        for update in ({"observed_at": "2026-10-03T09:00:00"}, {"schema_version": True},
                       {"schema_version": 2}, {"hex": "GG"}, {"origin": ""},
                       {"timing_issues": "bad"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_record({**record, **update})

    def test_invalid_json_has_line_number(self):
        with temporary_directory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text("{bad\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Line 1"):
                load_records(path)

    def test_utf8_bom_and_blank_lines(self):
        with temporary_directory() as directory:
            path = Path(directory) / "session.jsonl"
            record = demo_records()[0]
            path.write_text("\n" + json.dumps(record) + "\n\n", encoding="utf-8-sig")
            self.assertEqual(load_records(path), [record])

    def test_timing_issue_overrides_inferred_direction(self):
        record = {**demo_records()[0], "timing_issues": ["Inter-character silence exceeds t1.5"]}
        analyzed = analyze_record(record)
        self.assertTrue(analyzed["decoded"]["crc_valid"])
        self.assertEqual(analyzed["decoded"]["role"], "unknown")

    def test_short_frame_is_not_counted_as_crc_mismatch(self):
        record = {**demo_records()[0], "hex": "01 03"}
        summary = summarize([analyze_record(record)])
        self.assertEqual(summary["crc_errors"], 0)
        self.assertEqual(summary["frames_with_issues"], 1)

    def test_csv_retains_numeric_values_and_neutralizes_formulas(self):
        with temporary_directory() as directory:
            path = Path(directory) / "export.csv"
            record = {**demo_records()[-1], "session_id": "=1+1"}
            export_csv([analyze_record(record)], path)
            with path.open(newline="", encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["session_id"], "'=1+1")
            self.assertEqual(float(row["current_ma"]), 21)
            self.assertEqual(row["range_status"], "above_range")

    def test_report_escapes_script_injection(self):
        with temporary_directory() as directory:
            path = Path(directory) / "report.html"
            attack = "</script><script>alert(1)</script>"
            record = {**demo_records()[-1], "session_id": attack}
            render_report([analyze_record(record)], path)
            html = path.read_text(encoding="utf-8")
            self.assertNotIn(attack, html)
            self.assertIn("\\u003c/script>", html)
            self.assertNotIn("/*SESSION_DATA*/null", html)


class CliTests(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(args)
        return status, out.getvalue(), err.getvalue()

    def test_demo_to_replay_report_and_byte_framing(self):
        with temporary_directory() as directory:
            base = Path(directory)
            status, _, err = self.invoke(["demo", "--output", directory])
            self.assertEqual((status, err), (0, ""))
            for name in ("session.jsonl", "report.html", "measurements.csv", "bytes.jsonl"):
                self.assertTrue((base / name).is_file())
            status, output, _ = self.invoke(["replay", str(base / "session.jsonl")])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output)["summary"]["records"], 14)
            status, _, _ = self.invoke(["report", str(base / "session.jsonl"),
                                        "--output", str(base / "second.html")])
            self.assertEqual(status, 0)
            framed = base / "framed.jsonl"
            status, _, err = self.invoke(["frame-bytes", str(base / "bytes.jsonl"),
                                          "--output", str(framed), "--origin", "simulated",
                                          "--start", "2026-10-03T09:00:00+07:00"])
            self.assertEqual((status, err), (0, ""))
            records = load_records(framed)
            self.assertEqual(len(records), 2)
            self.assertTrue(all(analyze_record(r)["decoded"]["crc_valid"] for r in records))

    def test_decode_exit_status(self):
        status, _, _ = self.invoke(["decode", "01 03 00 00 00 0A C5 CD"])
        self.assertEqual(status, 0)
        status, _, _ = self.invoke(["decode", "01 03 00 00 00 0A CD C5"])
        self.assertEqual(status, 1)
        status, _, err = self.invoke(["decode", "GG"])
        self.assertEqual(status, 2)
        self.assertNotIn("Traceback", err)

    def test_missing_file_and_nan_have_clean_errors(self):
        with temporary_directory() as directory:
            status, _, err = self.invoke(["replay", str(Path(directory) / "missing.jsonl")])
            self.assertEqual(status, 2)
            self.assertNotIn("Traceback", err)
        status, _, err = self.invoke(["loop", "--current", "nan"])
        self.assertEqual(status, 2)
        self.assertNotIn("Traceback", err)

    def test_output_cannot_overwrite_capture(self):
        with temporary_directory() as directory:
            path = Path(directory) / "session.jsonl"
            save_records(demo_records(), path)
            before = path.read_bytes()
            for args in (["replay", str(path), "--csv", str(path)],
                         ["report", str(path), "--output", str(path)]):
                status, _, err = self.invoke(args)
                self.assertEqual(status, 2)
                self.assertIn("Output must differ", err)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()


class TransactionTests(unittest.TestCase):
    def frames(self, *payloads, session="s", start=0):
        from pocket_debugger.modbus import with_crc
        records = []
        for index, (offset_ms, payload, raw) in enumerate(payloads, 1):
            data = bytes.fromhex(payload)
            records.append(analyze_record({
                "schema_version": 1, "session_id": session, "record_id": f"f{index}",
                "observed_at": f"2026-10-03T09:00:{offset_ms // 1000:02}.{offset_ms % 1000:03}+07:00",
                "origin": "simulated", "kind": "modbus",
                "hex": (data if raw else with_crc(data)).hex(" ").upper(),
            }))
        return records

    def test_request_response_pair_with_turnaround(self):
        records = self.frames((0, "01 03 00 00 00 02", False), (25, "01 03 04 00 64 00 C8", False))
        transactions = pair_transactions(records)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["outcome"], "paired")
        self.assertEqual((transactions[0]["request_id"], transactions[0]["response_id"]), ("f1", "f2"))
        self.assertEqual(transactions[0]["turnaround_ms"], 25.0)
        self.assertFalse(transactions[0]["exception"])

    def test_exception_response_pairs_and_is_flagged(self):
        records = self.frames((0, "01 04 00 00 00 01", False), (10, "01 84 02", False))
        transaction = pair_transactions(records)[0]
        self.assertEqual(transaction["outcome"], "paired")
        self.assertTrue(transaction["exception"])
        self.assertEqual(transaction["function"], 4)

    def test_other_address_or_corrupt_frame_leaves_request_unmatched(self):
        records = self.frames((0, "01 03 00 00 00 02", False), (10, "02 03 04 00 64 00 C8", False))
        outcomes = [t["outcome"] for t in pair_transactions(records)]
        self.assertEqual(outcomes, ["unmatched"])
        records = self.frames((0, "01 03 00 00 00 02", False), (10, "01 03 04 00 64 00 00 00", True))
        self.assertEqual([t["outcome"] for t in pair_transactions(records)], ["unmatched"])

    def test_ambiguous_write_echo_is_never_paired(self):
        records = self.frames((0, "01 06 00 10 00 01", False), (10, "01 06 00 10 00 01", False))
        self.assertEqual(pair_transactions(records), [])

    def test_broadcast_requests_do_not_wait_for_a_response(self):
        records = self.frames((0, "00 06 00 10 00 01", False), (10, "01 03 00 00 00 02", False))
        outcomes = [t["outcome"] for t in pair_transactions(records)]
        self.assertEqual(outcomes, ["broadcast", "unmatched"])

    def test_sessions_are_paired_independently(self):
        first = self.frames((0, "01 03 00 00 00 02", False), session="a")
        second = self.frames((5, "01 03 04 00 64 00 C8", False), session="b")
        self.assertEqual([t["outcome"] for t in pair_transactions(first + second)], ["unmatched"])

    def test_demo_summary_counts_transactions(self):
        records = [analyze_record(r) for r in demo_records()]
        summary = summarize(records)
        self.assertEqual(summary["transactions_paired"], 2)
        self.assertEqual(summary["unmatched_requests"], 1)
        self.assertEqual(summary["broadcast_requests"], 0)
