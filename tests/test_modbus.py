import unittest

from pocket_debugger.modbus import RtuFramer, SerialTiming, crc16, decode_frame, with_crc


class DecoderTests(unittest.TestCase):
    def decode(self, payload):
        return decode_frame(with_crc(bytes.fromhex(payload)))

    def test_published_read_request_crc_vector(self):
        # Widely documented RTU vector; independent of with_crc round trips.
        raw = bytes.fromhex("01 03 00 00 00 0A C5 CD")
        self.assertEqual(crc16(raw[:-2]), 0xCDC5)
        result = decode_frame(raw)
        self.assertTrue(result["crc_valid"])
        self.assertEqual(result["role"], "request")
        self.assertEqual(result["candidates"][0]["quantity"], 10)

    def test_crc_wire_order_matters(self):
        result = decode_frame(bytes.fromhex("01 03 00 00 00 0A CD C5"))
        self.assertFalse(result["crc_valid"])
        self.assertEqual(result["role"], "unknown")

    def test_read_register_response_big_endian(self):
        result = self.decode("01 03 06 02 2B 00 00 00 64")
        self.assertEqual(result["role"], "response")
        self.assertEqual(result["candidates"][0]["registers"], [555, 0, 100])

    def test_exception(self):
        result = self.decode("01 83 02")
        self.assertEqual(result["role"], "response")
        self.assertEqual(result["candidates"][0]["exception_name"], "Illegal data address")

    def test_unknown_exception_flagged(self):
        result = self.decode("01 83 7F")
        self.assertIn("Unrecognized exception code", result["issues"])

    def test_write_single_echo_is_ambiguous(self):
        self.assertEqual(self.decode("01 06 00 10 00 01")["role"], "ambiguous")
        self.assertEqual(self.decode("01 05 00 10 FF 00")["role"], "ambiguous")

    def test_read_coil_shape_can_be_ambiguous(self):
        result = self.decode("01 01 03 00 00 08")
        self.assertEqual(result["role"], "ambiguous")

    def test_coils_padding_is_not_reported_as_quantity(self):
        result = self.decode("01 01 01 07")
        self.assertEqual(result["role"], "response")
        self.assertNotIn("quantity", result["candidates"][0])

    def test_write_multiple_request_and_response(self):
        request = self.decode("01 10 00 10 00 02 04 00 01 00 02")
        response = self.decode("01 10 00 10 00 02")
        self.assertEqual(request["role"], "request")
        self.assertEqual(response["role"], "response")
        self.assertEqual(request["candidates"][0]["quantity"], 2)

    def test_write_multiple_coils(self):
        self.assertEqual(self.decode("01 0F 00 10 00 09 02 FF 01")["role"], "request")

    def test_bad_quantity_and_address_overflow(self):
        for payload in ("01 03 00 00 00 00", "01 03 00 00 00 7E", "01 03 FF FF 00 02"):
            with self.subTest(payload=payload):
                self.assertTrue(self.decode(payload)["issues"])

    def test_wrong_response_byte_count(self):
        self.assertTrue(self.decode("01 03 04 00 64")["issues"])

    def test_odd_register_byte_count_rejected(self):
        self.assertTrue(self.decode("01 03 03 00 64 00")["issues"])

    def test_invalid_coil_write_value(self):
        self.assertTrue(self.decode("01 05 00 10 00 01")["issues"])

    def test_bad_multi_write_byte_count(self):
        self.assertTrue(self.decode("01 10 00 10 00 02 02 00 01 00 02")["issues"])

    def test_wrong_length_supported_function_is_not_reported_as_unsupported(self):
        for payload in ("01 06 00 10 00", "01 05 00 10 00 01 02"):
            result = self.decode(payload)
            self.assertEqual(result["issues"], ["Invalid length or values for this function"])
            self.assertEqual(result["function_name"], "Write single register" if payload.startswith("01 06") else "Write single coil")

    def test_broadcast_write_is_request(self):
        self.assertEqual(self.decode("00 06 00 10 00 01")["role"], "request")

    def test_broadcast_read_and_exception_rejected(self):
        for payload in ("00 03 00 00 00 01", "00 83 02"):
            self.assertTrue(self.decode(payload)["issues"])

    def test_reserved_address_flagged(self):
        self.assertTrue(self.decode("F8 03 00 00 00 01")["issues"])

    def test_unknown_function_retains_bytes(self):
        result = self.decode("01 41 01 02")
        self.assertTrue(result["crc_valid"])
        self.assertEqual(result["role"], "unknown")
        self.assertEqual(result["hex"], with_crc(bytes.fromhex("01 41 01 02")).hex(" ").upper())

    def test_short_frame_has_unknown_crc(self):
        for raw in (b"", b"\x01", b"\x01\x03\x00"):
            result = decode_frame(raw)
            self.assertIsNone(result["crc_valid"])
            self.assertTrue(result["issues"])

    def test_oversized_frame_flagged(self):
        result = decode_frame(with_crc(bytes([1, 3]) + bytes(253)))
        self.assertTrue(any("256-byte" in issue for issue in result["issues"]))


class TimingTests(unittest.TestCase):
    def test_9600_timing(self):
        timing = SerialTiming()
        self.assertAlmostEqual(timing.character_us, 1145.833333, places=5)
        self.assertAlmostEqual(timing.t3_5_us, 4010.416667, places=5)

    def test_fast_fixed_timing(self):
        timing = SerialTiming(38400)
        self.assertEqual(timing.t1_5_us, 750)
        self.assertEqual(timing.t3_5_us, 1750)

    def test_no_parity_uses_two_stop_bits(self):
        self.assertEqual(SerialTiming(9600, "N", 2).character_us, SerialTiming().character_us)
        with self.assertRaises(ValueError):
            SerialTiming(9600, "N", 1)

    def test_exact_boundary_and_final_frame(self):
        framer = RtuFramer()
        char = framer.timing.character_us
        self.assertIsNone(framer.feed(1, char))
        self.assertIsNone(framer.feed(3, 2 * char))
        frame = framer.feed(2, 3 * char + framer.timing.t3_5_us)
        self.assertEqual(frame["hex"], "01 03")
        self.assertTrue(frame["trailing_silence_verified"])
        last = framer.finish()
        self.assertEqual(last["hex"], "02")
        self.assertFalse(last["trailing_silence_verified"])
        self.assertIsNone(framer.finish())

    def test_long_intercharacter_silence_retained_and_flagged(self):
        framer = RtuFramer()
        char = framer.timing.character_us
        framer.feed(1, char)
        framer.feed(3, 2 * char + 2 * char)
        frame = framer.finish()
        self.assertEqual(frame["hex"], "01 03")
        self.assertEqual(len(frame["timing_issues"]), 1)

    def test_t1_5_exact_not_flagged(self):
        framer = RtuFramer()
        char = framer.timing.character_us
        framer.feed(1, char)
        framer.feed(3, 2 * char + framer.timing.t1_5_us)
        self.assertFalse(framer.finish()["timing_issues"])

    def test_overlapping_timestamps_rejected(self):
        framer = RtuFramer()
        framer.feed(1, 2000)
        with self.assertRaises(ValueError):
            framer.feed(3, 2500)

    def test_bad_byte_and_timestamp(self):
        for byte, stamp in ((256, 1000), (True, 1000), (1, -1), (1, float("nan")), (1, "1000")):
            with self.subTest(byte=byte, stamp=stamp), self.assertRaises(ValueError):
                RtuFramer().feed(byte, stamp)

    def test_buffer_is_bounded(self):
        framer = RtuFramer()
        char = framer.timing.character_us
        for index in range(4096):
            framer.feed(0, (index + 1) * char)
        with self.assertRaises(ValueError):
            framer.feed(0, 4097 * char)


if __name__ == "__main__":
    unittest.main()
